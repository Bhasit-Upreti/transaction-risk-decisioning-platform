"""
Unit tests for Manual Review Queue filtering.
Verifies that only automated 'Review' decisions enter the queue,
and that status filtering behaves correctly for Pending, In Progress, and completed reviews.
"""

import pytest
import pandas as pd
from pathlib import Path
from src.database import DatabaseManager


@pytest.fixture
def isolated_db(tmp_path: Path):
    db_file = tmp_path / "test_queue.db"
    return DatabaseManager(db_path=db_file)


def test_review_queue_filtering_by_decision_and_status(isolated_db):
    """
    Verifies that only 'Review' decisions enter the review queue.
    Approve and Decline transactions must never appear in this queue.
    """
    # 1. Insert 3 transactions with different decisions
    tx_df = pd.DataFrame([
        {
            "transaction_id": "TXN-REV-1",
            "customer_id": "C-1",
            "amount": 18000.0,
            "currency": "INR",
            "timestamp": "2026-10-02 12:00:00",
            "merchant_category": "Retail",
            "country": "IN",
            "payment_method": "Card",
            "customer_avg_amount": 2000.0,
            "customer_home_country": "IN",
            "source": "test",
        },
        {
            "transaction_id": "TXN-APP-1",
            "customer_id": "C-2",
            "amount": 500.0,
            "currency": "INR",
            "timestamp": "2026-10-02 12:05:00",
            "merchant_category": "Grocery",
            "country": "IN",
            "payment_method": "UPI",
            "customer_avg_amount": 600.0,
            "customer_home_country": "IN",
            "source": "test",
        },
        {
            "transaction_id": "TXN-DEC-1",
            "customer_id": "C-3",
            "amount": 75000.0,
            "currency": "INR",
            "timestamp": "2026-10-02 12:10:00",
            "merchant_category": "Crypto",
            "country": "SG",
            "payment_method": "Card",
            "customer_avg_amount": 1000.0,
            "customer_home_country": "IN",
            "source": "test",
        },
    ])
    isolated_db.save_valid_transactions(tx_df)

    decisions_df = pd.DataFrame([
        {
            "transaction_id": "TXN-REV-1",
            "risk_score": 50,
            "decision": "Review",
            "action_note": "Review queued",
            "triggered_rule_ids": "R001",
            "decision_explanation": "Test review",
            "rule_version": "v1.0.0",
        },
        {
            "transaction_id": "TXN-APP-1",
            "risk_score": 10,
            "decision": "Approve",
            "action_note": "Auto approved",
            "triggered_rule_ids": "None",
            "decision_explanation": "Test approve",
            "rule_version": "v1.0.0",
        },
        {
            "transaction_id": "TXN-DEC-1",
            "risk_score": 85,
            "decision": "Decline",
            "action_note": "Auto declined",
            "triggered_rule_ids": "R001, R004, R005",
            "decision_explanation": "Test decline",
            "rule_version": "v1.0.0",
        },
    ])
    isolated_db.save_decisions(decisions_df)

    # Test 1: Review decision, no review row explicitly written (defaults to Pending), filter All
    all_queue = isolated_db.get_review_queue(status_filter="All")
    assert len(all_queue) == 1
    assert all_queue.iloc[0]["transaction_id"] == "TXN-REV-1"
    assert all_queue.iloc[0]["review_status"] == "Pending"

    # Test 2: Approve decision excluded
    assert "TXN-APP-1" not in all_queue["transaction_id"].values

    # Test 3: Decline decision excluded
    assert "TXN-DEC-1" not in all_queue["transaction_id"].values

    # Test 4: Pending filter includes TXN-REV-1
    pending_queue = isolated_db.get_review_queue(status_filter="Pending")
    assert len(pending_queue) == 1
    assert pending_queue.iloc[0]["transaction_id"] == "TXN-REV-1"

    # Test 5: Analyst sets review to 'In Progress'
    isolated_db.record_review(
        transaction_id="TXN-REV-1",
        review_status="In Progress",
        reviewer_outcome="Under investigation",
        review_note="Checking with cardholder",
        reviewer_name="Analyst Bob",
    )

    # Filter 'Pending' should now exclude TXN-REV-1
    pending_after = isolated_db.get_review_queue(status_filter="Pending")
    assert len(pending_after) == 0

    # Filter 'In Progress' should include TXN-REV-1
    in_prog_queue = isolated_db.get_review_queue(status_filter="In Progress")
    assert len(in_prog_queue) == 1
    assert in_prog_queue.iloc[0]["transaction_id"] == "TXN-REV-1"
    assert in_prog_queue.iloc[0]["review_status"] == "In Progress"


def test_empty_review_queue_returns_expected_columns(isolated_db):
    """When no transactions exist, get_review_queue returns an empty DataFrame with proper schema."""
    empty_queue = isolated_db.get_review_queue(status_filter="All")
    assert empty_queue.empty
    expected_cols = [
        "transaction_id", "customer_id", "amount", "currency", "timestamp",
        "merchant_category", "country", "customer_avg_amount", "customer_home_country",
        "risk_score", "decision", "triggered_rule_ids", "decision_explanation",
        "review_status", "reviewer_outcome", "review_note", "reviewer_name", "reviewed_at"
    ]
    for col in expected_cols:
        assert col in empty_queue.columns
