"""
Decision Engine Module.
Maps risk scores and triggered rules to operational decisions (Approve, Review, Decline)
and creates transparent, human-readable explanations.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd
from src.rules import RuleOutcome
from config import DECISION_BANDS, RULE_VERSION, DEFAULT_DECISION


class DecisionEngine:
    """Evaluates risk scores against decision bands and generates explanations."""

    def __init__(
        self,
        decision_bands: Optional[Dict[str, Dict[str, Any]]] = None,
        rule_version: str = RULE_VERSION,
    ):
        self.decision_bands = decision_bands or DECISION_BANDS
        self.rule_version = rule_version

    def determine_decision(
        self,
        transaction_id: str,
        score_data: Dict[str, Any],
        rule_outcomes: List[RuleOutcome],
    ) -> Dict[str, Any]:
        """
        Determines the decision for a transaction and constructs explanation.

        Args:
            transaction_id: Unique identifier of the transaction.
            score_data: Result dictionary from RiskScoreCalculator.
            rule_outcomes: List of RuleOutcome objects.

        Returns:
            Dictionary with decision fields.
        """
        score = score_data["risk_score"]
        selected_decision = DEFAULT_DECISION
        action_note = "Automated risk policy evaluation."

        # Map score to decision band
        for band_key, band_cfg in self.decision_bands.items():
            if band_cfg["min_score"] <= score <= band_cfg["max_score"]:
                selected_decision = band_cfg["label"]
                action_note = band_cfg.get("action", "")
                break

        # Generate human-readable explanation
        triggered = [o for o in rule_outcomes if o.triggered]
        if not triggered:
            explanation = "No risk rules were triggered. Transaction is within normal behavioral parameters."
        else:
            reasons_list = [f"{o.name} ({o.points} pts: {o.reason})" for o in triggered]
            explanation = (
                f"Risk score of {score}/100 triggered {len(triggered)} rule(s): "
                + "; ".join(reasons_list)
                + f". Action mapped to '{selected_decision}'."
            )

        triggered_rule_ids_str = ", ".join(score_data["triggered_rule_ids"]) if score_data["triggered_rule_ids"] else "None"

        return {
            "transaction_id": transaction_id,
            "risk_score": score,
            "decision": selected_decision,
            "action_note": action_note,
            "triggered_rule_ids": triggered_rule_ids_str,
            "decision_explanation": explanation,
            "rule_version": self.rule_version,
            "decision_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def process_batch(
        self,
        valid_df: pd.DataFrame,
        batch_outcomes: List[List[RuleOutcome]],
        scores_data: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        """Processes an entire batch of scored transactions into a decisions DataFrame."""
        decision_records: List[Dict[str, Any]] = []

        for idx, row in valid_df.iterrows():
            tx_id = str(row["transaction_id"])
            outcomes = batch_outcomes[idx]
            score_data = scores_data[idx]

            dec = self.determine_decision(tx_id, score_data, outcomes)
            decision_records.append(dec)

        return pd.DataFrame(decision_records)


def make_decision(
    transaction_id: str,
    score_data: Dict[str, Any],
    rule_outcomes: List[RuleOutcome],
) -> Dict[str, Any]:
    """Helper function to determine decision for a single transaction."""
    engine = DecisionEngine()
    return engine.determine_decision(transaction_id, score_data, rule_outcomes)
