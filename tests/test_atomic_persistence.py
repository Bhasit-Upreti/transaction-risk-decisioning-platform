"""
Unit and integration tests for atomic persistence and database integrity.
Verifies that all accepted transaction artifacts (transactions, decisions, rule_evaluations)
commit together or roll back completely upon error, that duplicates cannot overwrite records,
and that foreign keys are strictly enforced.
"""

import pytest
import sqlite3
import pandas as pd
from pathlib import Path
from src.database import DatabaseManager
from src.pipeline import TransactionPipeline


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_atomic.db"
    return DatabaseManager(db_path=db_file)


def test_atomic_persistence_rollback_on_failure(temp_db, monkeypatch):
    """
    If a failure occurs during batch persistence (e.g., when saving rule evaluations),
    the entire transaction must be rolled back: no partial records in transactions or decisions.
    """
    pipeline = TransactionPipeline(db=temp_db)

    # 1 valid row, 1 invalid row
    batch = pd.DataFrame([
        {
            "transaction_id": "TXN-ROLLBACK-1",
            "customer_id": "C-1",
            "amount": 5000.0,
            "currency": "INR",
            "timestamp": "2026-10-02 10:00:00",
            "merchant_category": "Retail",
            "country": "IN",
            "payment_method": "Card",
            "customer_avg_amount": 1000.0,
            "customer_home_country": "IN",
        },
        {
            "transaction_id": "TXN-INV-1",
            "customer_id": "",  # invalid
            "amount": -50.0,
            "currency": "INR",
            "timestamp": "2026-10-02 10:05:00",
            "merchant_category": "Retail",
            "country": "IN",
            "payment_method": "Card",
        }
    ])

    # Inject simulated failure during save_rule_evaluations
    def failing_save_rule_evaluations(tx_id, outcomes, conn=None):
        raise RuntimeError("Simulated disk error during rule evaluation write")

    monkeypatch.setattr(temp_db, "save_rule_evaluations", failing_save_rule_evaluations)

    result = pipeline.process_transactions(batch)

    # Assert pipeline reports failure
    assert result["success"] is False
    assert "Atomic persistence failure" in result["message"] or "Persistence failed" in result["message"]

    # Assert NO partial records exist in transactions, decisions, or rule_evaluations
    with temp_db.get_connection() as conn:
        tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        dec_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        eval_count = conn.execute("SELECT COUNT(*) FROM rule_evaluations").fetchone()[0]
        val_count = conn.execute("SELECT COUNT(*) FROM validation_results").fetchone()[0]

    assert tx_count == 0, "Transactions table should be empty after rollback"
    assert dec_count == 0, "Decisions table should be empty after rollback"
    assert eval_count == 0, "Rule evaluations table should be empty after rollback"

    # Assert validation failure was preserved in validation_results
    assert val_count == 1, "Validation failure audit log should be preserved"


def test_immutable_transaction_id_no_silent_overwrite(temp_db):
    """
    Attempting to insert a duplicate transaction_id into transactions must raise
    IntegrityError rather than silently overwriting existing data.
    """
    row1 = pd.DataFrame([{
        "transaction_id": "TXN-IMMUTABLE",
        "customer_id": "C-ORIGINAL",
        "amount": 100.0,
        "currency": "INR",
        "timestamp": "2026-10-02 10:00:00",
        "merchant_category": "Retail",
        "country": "IN",
        "payment_method": "Card",
        "customer_avg_amount": 100.0,
        "customer_home_country": "IN",
        "source": "test",
    }])
    temp_db.save_valid_transactions(row1)

    # Duplicate row with modified amount
    row2 = pd.DataFrame([{
        "transaction_id": "TXN-IMMUTABLE",
        "customer_id": "C-MODIFIED",
        "amount": 9999.0,
        "currency": "INR",
        "timestamp": "2026-10-02 10:00:00",
        "merchant_category": "Retail",
        "country": "IN",
        "payment_method": "Card",
        "customer_avg_amount": 100.0,
        "customer_home_country": "IN",
        "source": "test",
    }])

    with pytest.raises(sqlite3.IntegrityError):
        temp_db.save_valid_transactions(row2)

    # Verify original row unchanged
    detail = temp_db.get_transaction_details("TXN-IMMUTABLE")
    assert detail["customer_id"] == "C-ORIGINAL"
    assert detail["amount"] == 100.0


def test_foreign_key_enforcement(temp_db):
    """Inserting a decision with a non-existent transaction_id must fail due to FK constraints."""
    decisions_df = pd.DataFrame([{
        "transaction_id": "TXN-DOES-NOT-EXIST",
        "risk_score": 10,
        "decision": "Approve",
        "action_note": "note",
        "triggered_rule_ids": "None",
        "decision_explanation": "exp",
        "rule_version": "v1.0.0",
        "decision_timestamp": "2026-10-02 10:00:00",
    }])

    with pytest.raises(sqlite3.IntegrityError):
        temp_db.save_decisions(decisions_df)


def test_successful_atomic_batch(temp_db):
    """A valid batch commits completely with transactions, decisions, and rule evaluations."""
    pipeline = TransactionPipeline(db=temp_db)
    batch = pd.DataFrame([{
        "transaction_id": "TXN-OK-1",
        "customer_id": "C-OK",
        "amount": 25000.0,
        "currency": "INR",
        "timestamp": "2026-10-02 10:00:00",
        "merchant_category": "Retail",
        "country": "IN",
        "payment_method": "Card",
        "customer_avg_amount": 2000.0,
        "customer_home_country": "IN",
    }])

    result = pipeline.process_transactions(batch)
    assert result["success"] is True

    detail = temp_db.get_transaction_details("TXN-OK-1")
    assert detail is not None
    assert detail["decision"] == "Review"
    assert len(detail["rule_evaluations"]) >= 4
