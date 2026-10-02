"""
Unit tests for data validation module.
Verifies completeness, data types, value constraints, and uniqueness checks.
"""

import pytest
import pandas as pd
from src.validation import TransactionValidator, validate_transactions


@pytest.fixture
def sample_valid_row():
    return {
        "transaction_id": "TXN-TEST-1",
        "customer_id": "CUST-100",
        "amount": 1500.0,
        "currency": "INR",
        "timestamp": "2026-10-02 10:00:00",
        "merchant_category": "Electronics",
        "country": "IN",
        "payment_method": "Card",
        "customer_avg_amount": 1200.0,
        "customer_home_country": "IN",
        "source": "test",
    }


def test_valid_transaction_passes(sample_valid_row):
    df = pd.DataFrame([sample_valid_row])
    valid_df, invalid_df, summary = validate_transactions(df)

    assert len(valid_df) == 1
    assert len(invalid_df) == 0
    assert summary["pass_rate"] == 100.0
    assert valid_df.iloc[0]["transaction_id"] == "TXN-TEST-1"
    assert valid_df.iloc[0]["amount"] == 1500.0


def test_missing_required_field_is_rejected(sample_valid_row):
    # Missing customer_id
    row = sample_valid_row.copy()
    row["customer_id"] = ""
    df = pd.DataFrame([row])
    valid_df, invalid_df, summary = validate_transactions(df)

    assert len(valid_df) == 0
    assert len(invalid_df) == 1
    assert "Missing or empty customer_id" in invalid_df.iloc[0]["error_reasons"]


def test_negative_or_zero_amount_is_rejected(sample_valid_row):
    row_neg = sample_valid_row.copy()
    row_neg["transaction_id"] = "TXN-NEG"
    row_neg["amount"] = -500.0

    row_zero = sample_valid_row.copy()
    row_zero["transaction_id"] = "TXN-ZERO"
    row_zero["amount"] = 0.0

    df = pd.DataFrame([row_neg, row_zero])
    valid_df, invalid_df, summary = validate_transactions(df)

    assert len(valid_df) == 0
    assert len(invalid_df) == 2
    for _, r in invalid_df.iterrows():
        assert "Amount must be greater than zero" in r["error_reasons"]


def test_non_numeric_amount_is_rejected(sample_valid_row):
    row = sample_valid_row.copy()
    row["amount"] = "INVALID_CHARS"
    df = pd.DataFrame([row])
    valid_df, invalid_df, _ = validate_transactions(df)

    assert len(valid_df) == 0
    assert len(invalid_df) == 1
    assert "must be a numeric value" in invalid_df.iloc[0]["error_reasons"]


def test_invalid_timestamp_is_rejected(sample_valid_row):
    row = sample_valid_row.copy()
    row["timestamp"] = "not_a_valid_date_time"
    df = pd.DataFrame([row])
    valid_df, invalid_df, _ = validate_transactions(df)

    assert len(valid_df) == 0
    assert len(invalid_df) == 1
    assert "Invalid timestamp format" in invalid_df.iloc[0]["error_reasons"]


def test_duplicate_transaction_id_in_batch_detected(sample_valid_row):
    row1 = sample_valid_row.copy()
    row2 = sample_valid_row.copy()  # Same TXN-TEST-1
    df = pd.DataFrame([row1, row2])
    valid_df, invalid_df, _ = validate_transactions(df)

    assert len(valid_df) == 1
    assert len(invalid_df) == 1
    assert "Duplicate transaction_id" in invalid_df.iloc[0]["error_reasons"]


def test_duplicate_against_existing_storage(sample_valid_row):
    existing_ids = {"TXN-TEST-1", "TXN-PREV-99"}
    df = pd.DataFrame([sample_valid_row])
    valid_df, invalid_df, _ = validate_transactions(df, existing_tx_ids=existing_ids)

    assert len(valid_df) == 0
    assert len(invalid_df) == 1
    assert "already exists in database" in invalid_df.iloc[0]["error_reasons"]


def test_unrecognized_currency_and_country(sample_valid_row):
    row = sample_valid_row.copy()
    row["currency"] = "FAKE_CURR"
    row["country"] = "FAKE_CTRY"
    df = pd.DataFrame([row])
    valid_df, invalid_df, _ = validate_transactions(df)

    assert len(valid_df) == 0
    assert len(invalid_df) == 1
    errs = invalid_df.iloc[0]["error_reasons"]
    assert "Unrecognized currency" in errs
    assert "Unrecognized country" in errs
