"""
Unit tests for decision mapping and explainability.
Verifies decision band mappings (Approve, Review, Decline) and explanation text.
"""

from src.decision import DecisionEngine
from src.rules import RuleOutcome


def test_decision_boundary_mapping():
    engine = DecisionEngine()

    dummy_outcomes = [RuleOutcome("R001", "High Value", False, 0, "Normal", "")]

    # Boundary 0 -> Approve
    dec_0 = engine.determine_decision("TXN-0", {"risk_score": 0, "triggered_rule_ids": []}, dummy_outcomes)
    assert dec_0["decision"] == "Approve"

    # Boundary 29 -> Approve
    dec_29 = engine.determine_decision("TXN-29", {"risk_score": 29, "triggered_rule_ids": []}, dummy_outcomes)
    assert dec_29["decision"] == "Approve"

    # Boundary 30 -> Review
    dec_30 = engine.determine_decision("TXN-30", {"risk_score": 30, "triggered_rule_ids": ["R001"]}, [
        RuleOutcome("R001", "High Value", True, 30, "Over threshold", "")
    ])
    assert dec_30["decision"] == "Review"

    # Boundary 69 -> Review
    dec_69 = engine.determine_decision("TXN-69", {"risk_score": 69, "triggered_rule_ids": ["R001"]}, dummy_outcomes)
    assert dec_69["decision"] == "Review"

    # Boundary 70 -> Decline
    dec_70 = engine.determine_decision("TXN-70", {"risk_score": 70, "triggered_rule_ids": ["R001", "R002", "R004"]}, [
        RuleOutcome("R001", "High Value", True, 30, "Reason 1", ""),
        RuleOutcome("R002", "Spike", True, 25, "Reason 2", ""),
        RuleOutcome("R004", "Country Mismatch", True, 20, "Reason 3", ""),
    ])
    assert dec_70["decision"] == "Decline"

    # Boundary 100 -> Decline
    dec_100 = engine.determine_decision("TXN-100", {"risk_score": 100, "triggered_rule_ids": []}, dummy_outcomes)
    assert dec_100["decision"] == "Decline"


def test_decision_explanation_generation():
    engine = DecisionEngine()
    outcomes = [
        RuleOutcome("R001", "High Value", True, 30, "Amount exceeds 15,000", ""),
        RuleOutcome("R004", "Country Mismatch", True, 20, "SG != IN", ""),
    ]
    score_data = {
        "risk_score": 50,
        "triggered_rule_ids": ["R001", "R004"],
    }
    dec = engine.determine_decision("TXN-EXP", score_data, outcomes)

    assert dec["decision"] == "Review"
    assert "High Value" in dec["decision_explanation"]
    assert "Country Mismatch" in dec["decision_explanation"]
    assert "50/100" in dec["decision_explanation"]
