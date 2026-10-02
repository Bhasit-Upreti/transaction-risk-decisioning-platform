"""
Integration tests for the end-to-end transaction risk pipeline.
Verifies complete flow: Ingestion -> Validation -> Rules -> Scoring -> Decision -> SQLite Persistence -> Manual Review.
"""

import pytest
import pandas as pd
from pathlib import Path
from src.database import DatabaseManager
from src.pipeline import TransactionPipeline
from src.ingestion import ingest_csv
from src.generator import generate_synthetic_transactions


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_risk.db"
    return DatabaseManager(db_path=db_file)


def test_end_to_end_pipeline_with_synthetic(temp_db):
    pipeline = TransactionPipeline(db=temp_db)

    # Generate 20 transactions, some invalid
    batch_df = generate_synthetic_transactions(n_records=20, include_invalid=True, invalid_ratio=0.25, seed=42)

    result = pipeline.process_transactions(batch_df)

    assert result["success"] is True
    assert result["total_records"] == 20
    assert result["valid_count"] > 0
    assert result["invalid_count"] > 0
    assert result["valid_count"] + result["invalid_count"] == 20

    # Verify transactions in SQLite
    full_df = temp_db.get_full_transactions()
    assert len(full_df) == result["valid_count"]

    # Verify invalid records logged in SQLite
    invalid_logs = temp_db.get_validation_failures()
    assert len(invalid_logs) == result["invalid_count"]

    # Verify decisions
    assert "decision" in full_df.columns
    assert "risk_score" in full_df.columns
    assert full_df["risk_score"].between(0, 100).all()


def test_rejection_isolation(temp_db):
    pipeline = TransactionPipeline(db=temp_db)

    # 1 valid, 1 completely broken row
    records = [
        {
            "transaction_id": "TXN-GOOD",
            "customer_id": "C-1",
            "amount": 100.0,
            "currency": "INR",
            "timestamp": "2026-10-02 12:00:00",
            "merchant_category": "Retail",
            "country": "IN",
            "payment_method": "Card",
            "customer_avg_amount": 100.0,
            "customer_home_country": "IN",
        },
        {
            "transaction_id": "TXN-BAD",
            "customer_id": "",  # missing!
            "amount": -50.0,    # negative!
            "currency": "FAKE",
            "timestamp": "bad_date",
            "merchant_category": "Retail",
            "country": "ZZ",
            "payment_method": "Card",
        }
    ]
    df = pd.DataFrame(records)
    result = pipeline.process_transactions(df)

    assert result["valid_count"] == 1
    assert result["invalid_count"] == 1

    stored_tx = temp_db.get_full_transactions()
    assert len(stored_tx) == 1
    assert stored_tx.iloc[0]["transaction_id"] == "TXN-GOOD"

    failures = temp_db.get_validation_failures()
    assert len(failures) == 1
    assert failures.iloc[0]["transaction_id"] == "TXN-BAD"


def test_manual_review_flow(temp_db):
    pipeline = TransactionPipeline(db=temp_db)

    # Transaction that maps to Review decision (score 30-69, triggers R001 = 30 pts)
    review_risk_record = {
        "transaction_id": "TXN-REVIEW-ME",
        "customer_id": "C-REVIEW",
        "amount": 18000.0,
        "currency": "INR",
        "timestamp": "2026-10-02 12:00:00",
        "merchant_category": "Electronics",
        "country": "IN",
        "payment_method": "Card",
        "customer_avg_amount": 18000.0,
        "customer_home_country": "IN",
    }
    df = pd.DataFrame([review_risk_record])
    pipeline.process_transactions(df)

    # Check that transaction is stored and queued
    tx_detail = temp_db.get_transaction_details("TXN-REVIEW-ME")
    assert tx_detail is not None
    assert tx_detail["review_status"] == "Pending"

    # Analyst records review
    success = temp_db.record_review(
        transaction_id="TXN-REVIEW-ME",
        review_status="Approved",
        reviewer_outcome="False Positive - Verified high-value holiday purchase with customer via phone",
        review_note="Customer confirmed travel to Singapore.",
        reviewer_name="Senior Analyst Alice",
    )
    assert success is True

    # Re-fetch and verify updated state
    updated_tx = temp_db.get_transaction_details("TXN-REVIEW-ME")
    assert updated_tx["review_status"] == "Approved"
    assert "Alice" in updated_tx["reviewer_name"]
    assert "False Positive" in updated_tx["reviewer_outcome"]


def test_csv_ingestion_helper(tmp_path):
    csv_file = tmp_path / "test_input.csv"
    csv_content = """transaction_id,customer_id,amount,currency,timestamp,merchant_category,country,payment_method,customer_avg_amount,customer_home_country
TXN-CSV-1,C-CSV-1,250.00,INR,2026-10-02 11:00:00,Grocery,IN,UPI,300.00,IN
"""
    csv_file.write_text(csv_content, encoding="utf-8")

    df, err = ingest_csv(str(csv_file))
    assert err is None
    assert len(df) == 1
    assert df.iloc[0]["transaction_id"] == "TXN-CSV-1"
    assert df.iloc[0]["source"] == "csv_upload"
