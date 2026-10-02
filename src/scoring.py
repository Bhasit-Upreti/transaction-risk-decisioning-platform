"""
Risk Scoring Engine Module.
Aggregates points from triggered business rules into a normalized, capped risk score.
"""

from typing import List, Dict, Any
from src.rules import RuleOutcome
from config import MAX_RISK_SCORE, MIN_RISK_SCORE


class RiskScoreCalculator:
    """Calculates illustrative risk scores from rule evaluation outcomes."""

    def __init__(self, max_score: int = MAX_RISK_SCORE, min_score: int = MIN_RISK_SCORE):
        self.max_score = max_score
        self.min_score = min_score

    def calculate_score(self, rule_outcomes: List[RuleOutcome]) -> Dict[str, Any]:
        """
        Calculates the risk score for a single transaction.

        Formula:
            risk_score = min(sum(triggered_rule_points), 100)

        Args:
            rule_outcomes: List of RuleOutcome objects for a transaction.

        Returns:
            Dictionary with scoring details:
                - risk_score: int (capped between min_score and max_score)
                - raw_score: int (uncapped sum)
                - triggered_rule_ids: List[str]
                - triggered_rule_names: List[str]
                - triggered_count: int
                - total_evaluated: int
        """
        raw_score = sum(outcome.points for outcome in rule_outcomes if outcome.triggered)
        capped_score = min(max(raw_score, self.min_score), self.max_score)

        triggered = [outcome for outcome in rule_outcomes if outcome.triggered]
        triggered_ids = [o.rule_id for o in triggered]
        triggered_names = [o.name for o in triggered]

        return {
            "risk_score": int(capped_score),
            "raw_score": int(raw_score),
            "triggered_rule_ids": triggered_ids,
            "triggered_rule_names": triggered_names,
            "triggered_count": len(triggered),
            "total_evaluated": len(rule_outcomes),
        }


def calculate_risk_score(rule_outcomes: List[RuleOutcome]) -> Dict[str, Any]:
    """Helper function to calculate risk score from rule outcomes."""
    calculator = RiskScoreCalculator()
    return calculator.calculate_score(rule_outcomes)
