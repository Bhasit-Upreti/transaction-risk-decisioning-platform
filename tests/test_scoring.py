"""
Unit tests for risk score calculation.
Verifies score aggregation, zero-handling, and the 100-point ceiling constraint.
"""

from src.scoring import RiskScoreCalculator
from src.rules import RuleOutcome


def test_zero_triggered_rules_gives_zero_score():
    calc = RiskScoreCalculator()
    outcomes = [
        RuleOutcome("R001", "High Value", False, 0, "Below threshold", ""),
        RuleOutcome("R002", "Spike", False, 0, "Normal ratio", ""),
    ]
    result = calc.calculate_score(outcomes)
    assert result["risk_score"] == 0
    assert result["raw_score"] == 0
    assert len(result["triggered_rule_ids"]) == 0
    assert result["triggered_count"] == 0


def test_points_summation():
    calc = RiskScoreCalculator()
    outcomes = [
        RuleOutcome("R001", "High Value", True, 30, "Triggered R001", ""),
        RuleOutcome("R002", "Spike", False, 0, "Normal", ""),
        RuleOutcome("R004", "Country Mismatch", True, 20, "Triggered R004", ""),
    ]
    result = calc.calculate_score(outcomes)
    assert result["risk_score"] == 50
    assert result["raw_score"] == 50
    assert result["triggered_rule_ids"] == ["R001", "R004"]
    assert result["triggered_count"] == 2


def test_score_capped_at_100():
    calc = RiskScoreCalculator()
    # Summing to 115 points
    outcomes = [
        RuleOutcome("R001", "High Value", True, 30, "Triggered", ""),
        RuleOutcome("R002", "Spike", True, 25, "Triggered", ""),
        RuleOutcome("R003", "Velocity", True, 25, "Triggered", ""),
        RuleOutcome("R004", "Country Mismatch", True, 20, "Triggered", ""),
        RuleOutcome("R005", "High-Risk Cat", True, 15, "Triggered", ""),
    ]
    result = calc.calculate_score(outcomes)
    assert result["raw_score"] == 115
    assert result["risk_score"] == 100  # Must be strictly capped at 100
