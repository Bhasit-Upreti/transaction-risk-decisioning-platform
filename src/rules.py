"""
Business Rule Engine Module.
Evaluates validated transactions against configurable business rules.
Produces structured rule outcomes with clear explanations and assigned points.
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import pandas as pd
from config import RULES_CONFIG


@dataclass
class RuleOutcome:
    """Individual rule evaluation result for a transaction."""
    rule_id: str
    name: str
    triggered: bool
    points: int
    reason: str
    threshold_info: str
    status: str = "evaluated"  # "evaluated", "not_evaluable", "skipped"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_velocity_count(
    transaction_id: str,
    customer_id: str,
    timestamp: Union[str, datetime, pd.Timestamp],
    prior_records: Optional[pd.DataFrame] = None,
    window_minutes: int = 30,
) -> int:
    """
    Computes deterministic velocity count for a customer within [T - window_minutes, T].
    Uses strict (timestamp, transaction_id) tie-breaking.
    Future transactions are excluded.
    Returns the total count including the transaction itself (at least 1).
    """
    if prior_records is None or prior_records.empty:
        return 1

    tx_dt = pd.to_datetime(timestamp)
    window_start = tx_dt - timedelta(minutes=window_minutes)
    current_key = (tx_dt, str(transaction_id))

    if "customer_id" not in prior_records.columns:
        return 1

    cust_records = prior_records[prior_records["customer_id"] == customer_id]
    if cust_records.empty:
        return 1

    prior_count = 0
    for _, row in cust_records.iterrows():
        r_dt = pd.to_datetime(row["timestamp"])
        r_id = str(row.get("transaction_id", ""))
        r_key = (r_dt, r_id)

        # Must fall within the inclusive window [window_start, tx_dt]
        # and be strictly earlier in the deterministic (timestamp, transaction_id) ordering
        if window_start <= r_dt <= tx_dt and r_key < current_key:
            prior_count += 1

    return prior_count + 1


class BusinessRuleEngine:
    """Configurable rule evaluation engine for transactions."""

    def __init__(self, config: Optional[Dict[str, Dict[str, Any]]] = None):
        self.rules_config = config or RULES_CONFIG

    def evaluate_transaction(
        self,
        transaction: Dict[str, Any],
        historical_context: Optional[pd.DataFrame] = None,
    ) -> List[RuleOutcome]:
        """
        Evaluates a single transaction against all enabled rules.

        Args:
            transaction: Dictionary of validated transaction fields.
            historical_context: Optional DataFrame of prior transactions for velocity calculation.

        Returns:
            List of RuleOutcome objects.
        """
        outcomes: List[RuleOutcome] = []

        tx_id = str(transaction.get("transaction_id", ""))
        amount = float(transaction.get("amount", 0.0))
        cust_id = str(transaction.get("customer_id", ""))
        country = str(transaction.get("country", "")).strip().upper()
        home_country = str(transaction.get("customer_home_country", "")).strip().upper()
        merchant_cat = str(transaction.get("merchant_category", "")).strip()

        # Parse transaction timestamp
        ts_val = transaction.get("timestamp")
        try:
            tx_dt = pd.to_datetime(ts_val)
        except Exception:
            tx_dt = datetime.now()

        # -------------------------------------------------------------
        # Rule R001: High-Value Amount (INR-denominated)
        # -------------------------------------------------------------
        cfg_r001 = self.rules_config.get("R001", {})
        if cfg_r001.get("enabled", True):
            threshold = float(cfg_r001.get("parameters", {}).get("amount_threshold", 15000.0))
            pts = int(cfg_r001.get("points", 30))
            if amount >= threshold:
                outcomes.append(RuleOutcome(
                    rule_id="R001",
                    name=cfg_r001.get("name", "High-Value Amount"),
                    triggered=True,
                    points=pts,
                    status="evaluated",
                    reason=f"Transaction amount ({amount:,.2f} INR) meets or exceeds high-value threshold ({threshold:,.2f} INR)",
                    threshold_info=f"Threshold: >= {threshold:,.2f} INR"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R001",
                    name=cfg_r001.get("name", "High-Value Amount"),
                    triggered=False,
                    points=0,
                    status="evaluated",
                    reason=f"Amount ({amount:,.2f} INR) is below high-value threshold ({threshold:,.2f} INR)",
                    threshold_info=f"Threshold: >= {threshold:,.2f} INR"
                ))

        # -------------------------------------------------------------
        # Rule R002: Spike vs Customer Average (INR-denominated)
        # -------------------------------------------------------------
        cfg_r002 = self.rules_config.get("R002", {})
        if cfg_r002.get("enabled", True):
            multiplier = float(cfg_r002.get("parameters", {}).get("multiplier", 3.0))
            min_excess = float(cfg_r002.get("parameters", {}).get("min_excess_amount", 2000.0))
            pts = int(cfg_r002.get("points", 25))

            cust_avg_raw = transaction.get("customer_avg_amount")
            has_baseline = (
                cust_avg_raw is not None
                and not pd.isna(cust_avg_raw)
                and str(cust_avg_raw).strip() not in ("", "nan", "None", "null")
            )
            parsed_cust_avg = None
            if has_baseline:
                try:
                    parsed_cust_avg = float(cust_avg_raw)
                    if parsed_cust_avg <= 0:
                        has_baseline = False
                except (ValueError, TypeError):
                    has_baseline = False

            if not has_baseline:
                outcomes.append(RuleOutcome(
                    rule_id="R002",
                    name=cfg_r002.get("name", "Unusual Spike vs Customer Average"),
                    triggered=False,
                    points=0,
                    status="not_evaluable",
                    reason="Customer historical baseline unavailable; spike rule not evaluable",
                    threshold_info=f"Threshold: >= {multiplier}x avg & >= +{min_excess:,.2f} INR"
                ))
            else:
                cust_avg = parsed_cust_avg
                is_spike = (amount >= multiplier * cust_avg) and ((amount - cust_avg) >= min_excess)
                ratio = (amount / cust_avg) if cust_avg > 0 else 1.0

                if is_spike:
                    outcomes.append(RuleOutcome(
                        rule_id="R002",
                        name=cfg_r002.get("name", "Unusual Spike vs Customer Average"),
                        triggered=True,
                        points=pts,
                        status="evaluated",
                        reason=f"Amount is {ratio:.1f}x higher than customer average ({cust_avg:,.2f} INR), exceeding {multiplier}x threshold",
                        threshold_info=f"Threshold: >= {multiplier}x avg & >= +{min_excess:,.2f} INR"
                    ))
                else:
                    outcomes.append(RuleOutcome(
                        rule_id="R002",
                        name=cfg_r002.get("name", "Unusual Spike vs Customer Average"),
                        triggered=False,
                        points=0,
                        status="evaluated",
                        reason=f"Amount ratio ({ratio:.1f}x) is within normal range of customer average ({cust_avg:,.2f} INR)",
                        threshold_info=f"Threshold: >= {multiplier}x avg"
                    ))

        # -------------------------------------------------------------
        # Rule R003: Velocity (Rapid Repeated Transactions)
        # -------------------------------------------------------------
        cfg_r003 = self.rules_config.get("R003", {})
        if cfg_r003.get("enabled", True):
            window_minutes = int(cfg_r003.get("parameters", {}).get("window_minutes", 30))
            count_thresh = int(cfg_r003.get("parameters", {}).get("count_threshold", 3))
            pts = int(cfg_r003.get("points", 25))

            recent_count = compute_velocity_count(
                transaction_id=tx_id,
                customer_id=cust_id,
                timestamp=tx_dt,
                prior_records=historical_context,
                window_minutes=window_minutes,
            )

            if recent_count >= count_thresh:
                outcomes.append(RuleOutcome(
                    rule_id="R003",
                    name=cfg_r003.get("name", "Rapid Velocity"),
                    triggered=True,
                    points=pts,
                    status="evaluated",
                    reason=f"Customer executed {recent_count} transactions within {window_minutes} minutes (limit: {count_thresh})",
                    threshold_info=f"Threshold: >= {count_thresh} txns in {window_minutes}m"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R003",
                    name=cfg_r003.get("name", "Rapid Velocity"),
                    triggered=False,
                    points=0,
                    status="evaluated",
                    reason=f"Velocity count ({recent_count}) is below limit ({count_thresh}) within {window_minutes}m window",
                    threshold_info=f"Threshold: >= {count_thresh} txns in {window_minutes}m"
                ))

        # -------------------------------------------------------------
        # Rule R004: Country Mismatch (Cross-Border)
        # -------------------------------------------------------------
        cfg_r004 = self.rules_config.get("R004", {})
        if cfg_r004.get("enabled", True):
            pts = int(cfg_r004.get("points", 20))
            # Triggered only when home_country is known and differs
            if home_country and country and home_country != country:
                outcomes.append(RuleOutcome(
                    rule_id="R004",
                    name=cfg_r004.get("name", "Country Mismatch"),
                    triggered=True,
                    points=pts,
                    status="evaluated",
                    reason=f"Transaction origin ({country}) does not match customer registered home country ({home_country})",
                    threshold_info="Condition: country != customer_home_country"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R004",
                    name=cfg_r004.get("name", "Country Mismatch"),
                    triggered=False,
                    points=0,
                    status="evaluated",
                    reason=f"Transaction country ({country}) matches customer home country ({home_country})",
                    threshold_info="Condition: country != customer_home_country"
                ))

        # -------------------------------------------------------------
        # Rule R005: High-Risk Merchant Category
        # -------------------------------------------------------------
        cfg_r005 = self.rules_config.get("R005", {})
        if cfg_r005.get("enabled", True):
            high_risk_cats = cfg_r005.get("parameters", {}).get(
                "high_risk_categories", ["Crypto", "Gambling"]
            )
            pts = int(cfg_r005.get("points", 15))
            if merchant_cat in high_risk_cats:
                outcomes.append(RuleOutcome(
                    rule_id="R005",
                    name=cfg_r005.get("name", "High-Risk Merchant Category"),
                    triggered=True,
                    points=pts,
                    status="evaluated",
                    reason=f"Merchant category '{merchant_cat}' is classified as high-risk ({', '.join(high_risk_cats)})",
                    threshold_info=f"Categories: {', '.join(high_risk_cats)}"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R005",
                    name=cfg_r005.get("name", "High-Risk Merchant Category"),
                    triggered=False,
                    points=0,
                    status="evaluated",
                    reason=f"Merchant category '{merchant_cat}' is not in high-risk list",
                    threshold_info=f"Categories: {', '.join(high_risk_cats)}"
                ))

        return outcomes

    def evaluate_batch(
        self,
        df: pd.DataFrame,
        historical_context: Optional[pd.DataFrame] = None,
    ) -> List[List[RuleOutcome]]:
        """
        Evaluates a batch of transactions deterministically.
        Sorts the batch by (timestamp, transaction_id) to build sequential prior context,
        then maps outcomes back to the original row order of df.
        Future transactions in the batch are never counted as prior activity.
        """
        if df.empty:
            return []

        # Prepare pre-batch historical pool
        hist_pool = (
            historical_context.copy()
            if historical_context is not None and not historical_context.empty
            else pd.DataFrame()
        )

        # Sort incoming batch deterministically by (timestamp, transaction_id)
        # to ensure evaluation is independent of input row order
        temp_df = df.copy()
        temp_df["_dt"] = pd.to_datetime(temp_df["timestamp"])
        temp_df["_tx_id"] = temp_df["transaction_id"].astype(str)
        sorted_indices = temp_df.sort_values(by=["_dt", "_tx_id"]).index.tolist()

        outcomes_by_idx: Dict[Any, List[RuleOutcome]] = {}
        cum_batch_records: List[Dict[str, Any]] = []

        for orig_idx in sorted_indices:
            row_dict = df.loc[orig_idx].to_dict()

            # Context consists of historical records + earlier records from this batch only
            if cum_batch_records:
                batch_so_far = pd.DataFrame(cum_batch_records)
                if not hist_pool.empty:
                    combined_ctx = pd.concat([hist_pool, batch_so_far], ignore_index=True)
                else:
                    combined_ctx = batch_so_far
            else:
                combined_ctx = hist_pool

            outcomes = self.evaluate_transaction(row_dict, historical_context=combined_ctx)
            outcomes_by_idx[orig_idx] = outcomes

            # Append this transaction to the cumulative batch records for subsequent transactions
            cum_batch_records.append(row_dict)

        # Return outcomes in original DataFrame row order
        return [outcomes_by_idx[idx] for idx in df.index]
