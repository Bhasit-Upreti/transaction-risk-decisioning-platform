"""
Business Rule Engine Module.
Evaluates validated transactions against configurable business rules.
Produces structured rule outcomes with clear explanations and assigned points.
"""

from typing import Dict, Any, List, Optional
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

        amount = float(transaction.get("amount", 0.0))
        cust_id = str(transaction.get("customer_id", ""))
        country = str(transaction.get("country", "")).strip().upper()
        home_country = str(transaction.get("customer_home_country", "")).strip().upper()
        cust_avg = float(transaction.get("customer_avg_amount", amount))
        merchant_cat = str(transaction.get("merchant_category", "")).strip()

        # Parse transaction timestamp
        ts_val = transaction.get("timestamp")
        try:
            tx_dt = pd.to_datetime(ts_val)
        except Exception:
            tx_dt = datetime.now()

        # -------------------------------------------------------------
        # Rule R001: High-Value Amount
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
                    reason=f"Transaction amount ({amount:,.2f}) meets or exceeds high-value threshold ({threshold:,.2f})",
                    threshold_info=f"Threshold: >= {threshold:,.2f}"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R001",
                    name=cfg_r001.get("name", "High-Value Amount"),
                    triggered=False,
                    points=0,
                    reason=f"Amount ({amount:,.2f}) is below high-value threshold ({threshold:,.2f})",
                    threshold_info=f"Threshold: >= {threshold:,.2f}"
                ))

        # -------------------------------------------------------------
        # Rule R002: Spike vs Customer Average
        # -------------------------------------------------------------
        cfg_r002 = self.rules_config.get("R002", {})
        if cfg_r002.get("enabled", True):
            multiplier = float(cfg_r002.get("parameters", {}).get("multiplier", 3.0))
            min_excess = float(cfg_r002.get("parameters", {}).get("min_excess_amount", 2000.0))
            pts = int(cfg_r002.get("points", 25))

            is_spike = (amount >= multiplier * cust_avg) and ((amount - cust_avg) >= min_excess)
            ratio = (amount / cust_avg) if cust_avg > 0 else 1.0

            if is_spike:
                outcomes.append(RuleOutcome(
                    rule_id="R002",
                    name=cfg_r002.get("name", "Unusual Spike vs Customer Average"),
                    triggered=True,
                    points=pts,
                    reason=f"Amount is {ratio:.1f}x higher than customer average ({cust_avg:,.2f}), exceeding {multiplier}x threshold",
                    threshold_info=f"Threshold: >= {multiplier}x avg & >= +{min_excess:,.2f}"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R002",
                    name=cfg_r002.get("name", "Unusual Spike vs Customer Average"),
                    triggered=False,
                    points=0,
                    reason=f"Amount ratio ({ratio:.1f}x) is within normal range of customer average ({cust_avg:,.2f})",
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

            # Count recent occurrences for this customer
            recent_count = 1
            if historical_context is not None and not historical_context.empty:
                try:
                    hist_dt = pd.to_datetime(historical_context["timestamp"])
                    time_diff = (tx_dt - hist_dt).dt.total_seconds() / 60.0
                    # Transactions by same customer within [0, window_minutes] before this transaction
                    in_window = (
                        (historical_context["customer_id"] == cust_id) &
                        (time_diff >= 0) &
                        (time_diff <= window_minutes) &
                        (historical_context["transaction_id"] != transaction.get("transaction_id"))
                    )
                    recent_count = int(in_window.sum()) + 1
                except Exception:
                    recent_count = 1

            if recent_count >= count_thresh:
                outcomes.append(RuleOutcome(
                    rule_id="R003",
                    name=cfg_r003.get("name", "Rapid Velocity"),
                    triggered=True,
                    points=pts,
                    reason=f"Customer executed {recent_count} transactions within {window_minutes} minutes (limit: {count_thresh})",
                    threshold_info=f"Threshold: >= {count_thresh} txns in {window_minutes}m"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R003",
                    name=cfg_r003.get("name", "Rapid Velocity"),
                    triggered=False,
                    points=0,
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
                    reason=f"Transaction origin ({country}) does not match customer registered home country ({home_country})",
                    threshold_info="Condition: country != customer_home_country"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R004",
                    name=cfg_r004.get("name", "Country Mismatch"),
                    triggered=False,
                    points=0,
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
                    reason=f"Merchant category '{merchant_cat}' is classified as high-risk ({', '.join(high_risk_cats)})",
                    threshold_info=f"Categories: {', '.join(high_risk_cats)}"
                ))
            else:
                outcomes.append(RuleOutcome(
                    rule_id="R005",
                    name=cfg_r005.get("name", "High-Risk Merchant Category"),
                    triggered=False,
                    points=0,
                    reason=f"Merchant category '{merchant_cat}' is not in high-risk list",
                    threshold_info=f"Categories: {', '.join(high_risk_cats)}"
                ))

        return outcomes

    def evaluate_batch(
        self,
        df: pd.DataFrame,
        historical_context: Optional[pd.DataFrame] = None,
    ) -> List[List[RuleOutcome]]:
        """Evaluates a batch of transactions and returns outcomes per transaction."""
        results: List[List[RuleOutcome]] = []
        if df.empty:
            return results

        # If historical_context is not provided, combine prior rows in df for internal velocity
        combined_context = df if historical_context is None else pd.concat([historical_context, df], ignore_index=True)

        for _, row in df.iterrows():
            outcomes = self.evaluate_transaction(row.to_dict(), historical_context=combined_context)
            results.append(outcomes)

        return results
