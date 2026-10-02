"""
Unit tests for business rule evaluation engine.
Verifies transparent logic, points assignment, missing baseline handling,
and deterministic velocity semantics for each rule.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from src.rules import BusinessRuleEngine, compute_velocity_count


@pytest.fixture
def rule_engine():
    return BusinessRuleEngine()


# -------------------------------------------------------------------
# R001: High-Value Amount (INR-denominated) Tests
# -------------------------------------------------------------------

def test_r001_high_value_rule_boundaries(rule_engine):
    base_tx = {
        "transaction_id": "TXN-1",
        "customer_id": "C-1",
        "currency": "INR",
        "customer_avg_amount": 2000.0,
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "timestamp": "2026-10-02 12:00:00",
    }

    # Exactly at threshold 15,000.00 INR -> triggers
    tx_exact = base_tx.copy()
    tx_exact["amount"] = 15000.0
    r001_exact = next(o for o in rule_engine.evaluate_transaction(tx_exact) if o.rule_id == "R001")
    assert r001_exact.triggered is True
    assert r001_exact.points == 30
    assert "15,000.00 INR" in r001_exact.reason

    # Just above threshold 15,000.01 INR -> triggers
    tx_above = base_tx.copy()
    tx_above["amount"] = 15000.01
    r001_above = next(o for o in rule_engine.evaluate_transaction(tx_above) if o.rule_id == "R001")
    assert r001_above.triggered is True
    assert r001_above.points == 30

    # Just below threshold 14,999.99 INR -> does not trigger
    tx_below = base_tx.copy()
    tx_below["amount"] = 14999.99
    r001_below = next(o for o in rule_engine.evaluate_transaction(tx_below) if o.rule_id == "R001")
    assert r001_below.triggered is False
    assert r001_below.points == 0


# -------------------------------------------------------------------
# R002: Spike vs Customer Average Tests
# -------------------------------------------------------------------

def test_r002_spike_vs_customer_average(rule_engine):
    # Customer avg is 1000 INR, multiplier is 3.0x -> amount 5000 is 5x, diff 4000 >= 2000 INR
    tx_spike = {
        "transaction_id": "TXN-2",
        "customer_id": "C-2",
        "amount": 5000.0,
        "currency": "INR",
        "customer_avg_amount": 1000.0,
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "timestamp": "2026-10-02 12:00:00",
    }
    outcomes = rule_engine.evaluate_transaction(tx_spike)
    r002 = next(o for o in outcomes if o.rule_id == "R002")
    assert r002.triggered is True
    assert r002.points == 25
    assert r002.status == "evaluated"

    # Normal amount: 1500 vs avg 1000
    tx_normal = tx_spike.copy()
    tx_normal["amount"] = 1500.0
    outcomes_normal = rule_engine.evaluate_transaction(tx_normal)
    r002_normal = next(o for o in outcomes_normal if o.rule_id == "R002")
    assert r002_normal.triggered is False
    assert r002_normal.points == 0
    assert r002_normal.status == "evaluated"


def test_r002_missing_baseline_not_evaluable(rule_engine):
    """
    When customer_avg_amount is absent or None, R002 must not masquerade as 'normal behavior'.
    It must be explicitly marked as not_evaluable with 0 points.
    """
    tx_no_baseline = {
        "transaction_id": "TXN-NO-BASE",
        "customer_id": "C-NO-BASE",
        "amount": 10000.0,
        "currency": "INR",
        "customer_avg_amount": None,
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "timestamp": "2026-10-02 12:00:00",
    }
    outcomes = rule_engine.evaluate_transaction(tx_no_baseline)
    r002 = next(o for o in outcomes if o.rule_id == "R002")
    assert r002.triggered is False
    assert r002.points == 0
    assert r002.status == "not_evaluable"
    assert "baseline unavailable" in r002.reason.lower()


# -------------------------------------------------------------------
# R003: Velocity Tests (Deterministic semantics & boundaries)
# -------------------------------------------------------------------

def test_compute_velocity_count_boundaries():
    t_curr = datetime(2026, 10, 2, 10, 30, 0)
    cust_id = "CUST-VEL"

    # 1. Transaction exactly 30 minutes earlier (10:00:00 vs 10:30:00) -> INCLUSIVE, counts!
    # 2. Transaction 20 minutes earlier (10:10:00) -> counts!
    # 3. Transaction 31 minutes earlier (09:59:00) -> outside 30m window, does NOT count!
    # 4. Future transaction (10:31:00) -> does NOT count!
    # 5. Transaction from another customer -> does NOT count!
    records = pd.DataFrame([
        {"transaction_id": "T-30MIN-AGO", "customer_id": cust_id, "timestamp": "2026-10-02 10:00:00"},
        {"transaction_id": "T-20MIN-AGO", "customer_id": cust_id, "timestamp": "2026-10-02 10:10:00"},
        {"transaction_id": "T-31MIN-AGO", "customer_id": cust_id, "timestamp": "2026-10-02 09:59:00"},
        {"transaction_id": "T-FUTURE", "customer_id": cust_id, "timestamp": "2026-10-02 10:31:00"},
        {"transaction_id": "T-OTHER-CUST", "customer_id": "OTHER", "timestamp": "2026-10-02 10:15:00"},
    ])

    count = compute_velocity_count(
        transaction_id="T-CURRENT",
        customer_id=cust_id,
        timestamp=t_curr,
        prior_records=records,
        window_minutes=30,
    )

    # Expected: T-30MIN-AGO (1) + T-20MIN-AGO (1) + Current Transaction (1) = 3
    assert count == 3


def test_velocity_deterministic_tie_break_same_timestamp():
    """When transactions share the exact same timestamp, tie-break by transaction_id."""
    t_shared = "2026-10-02 11:00:00"
    cust_id = "C-TIE"

    # TXN-A is lexicographically smaller than TXN-B
    records = pd.DataFrame([
        {"transaction_id": "TXN-A", "customer_id": cust_id, "timestamp": t_shared},
    ])

    # Evaluating TXN-B with TXN-A in history
    count_b = compute_velocity_count("TXN-B", cust_id, t_shared, records, window_minutes=30)
    assert count_b == 2  # TXN-A is prior, so count = 2

    # Evaluating TXN-A with TXN-B in history
    records_b = pd.DataFrame([
        {"transaction_id": "TXN-B", "customer_id": cust_id, "timestamp": t_shared},
    ])
    count_a = compute_velocity_count("TXN-A", cust_id, t_shared, records_b, window_minutes=30)
    assert count_a == 1  # TXN-B is NOT prior to TXN-A, so count = 1


def test_evaluate_batch_order_invariance(rule_engine):
    """
    Reversing the input DataFrame row order must not change decisions or velocity counts.
    """
    cust_id = "C-INVAR"
    t0 = datetime(2026, 10, 2, 10, 0, 0)

    # 3 transactions for same customer within 10 minutes
    tx1 = {
        "transaction_id": "TXN-1",
        "customer_id": cust_id,
        "amount": 1000.0,
        "currency": "INR",
        "customer_avg_amount": 1000.0,
        "timestamp": t0.strftime("%Y-%m-%d %H:%M:%S"),
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
    }
    tx2 = {
        "transaction_id": "TXN-2",
        "customer_id": cust_id,
        "amount": 1000.0,
        "currency": "INR",
        "customer_avg_amount": 1000.0,
        "timestamp": (t0 + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
    }
    tx3 = {
        "transaction_id": "TXN-3",
        "customer_id": cust_id,
        "amount": 1000.0,
        "currency": "INR",
        "customer_avg_amount": 1000.0,
        "timestamp": (t0 + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
    }

    forward_df = pd.DataFrame([tx1, tx2, tx3])
    reverse_df = pd.DataFrame([tx3, tx2, tx1])

    outcomes_fwd = rule_engine.evaluate_batch(forward_df)
    outcomes_rev = rule_engine.evaluate_batch(reverse_df)

    # In forward_df:
    # TXN-1 has count 1 (no trigger)
    # TXN-2 has count 2 (no trigger)
    # TXN-3 has count 3 (triggers R003)
    r003_fwd_1 = next(o for o in outcomes_fwd[0] if o.rule_id == "R003")
    r003_fwd_2 = next(o for o in outcomes_fwd[1] if o.rule_id == "R003")
    r003_fwd_3 = next(o for o in outcomes_fwd[2] if o.rule_id == "R003")

    assert r003_fwd_1.triggered is False
    assert r003_fwd_2.triggered is False
    assert r003_fwd_3.triggered is True

    # In reverse_df:
    # index 0 is TXN-3 -> must trigger R003
    # index 1 is TXN-2 -> must NOT trigger
    # index 2 is TXN-1 -> must NOT trigger
    r003_rev_3 = next(o for o in outcomes_rev[0] if o.rule_id == "R003")
    r003_rev_2 = next(o for o in outcomes_rev[1] if o.rule_id == "R003")
    r003_rev_1 = next(o for o in outcomes_rev[2] if o.rule_id == "R003")

    assert r003_rev_3.triggered is True
    assert r003_rev_2.triggered is False
    assert r003_rev_1.triggered is False


# -------------------------------------------------------------------
# R004 and R005 Tests
# -------------------------------------------------------------------

def test_r004_country_mismatch_rule(rule_engine):
    tx_mismatch = {
        "transaction_id": "TXN-CROSS",
        "customer_id": "C-3",
        "amount": 1000.0,
        "currency": "INR",
        "country": "SG",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "customer_avg_amount": 1000.0,
        "timestamp": "2026-10-02 12:00:00",
    }
    outcomes = rule_engine.evaluate_transaction(tx_mismatch)
    r004 = next(o for o in outcomes if o.rule_id == "R004")
    assert r004.triggered is True
    assert r004.points == 20

    tx_match = tx_mismatch.copy()
    tx_match["country"] = "IN"
    outcomes_match = rule_engine.evaluate_transaction(tx_match)
    r004_match = next(o for o in outcomes_match if o.rule_id == "R004")
    assert r004_match.triggered is False
    assert r004_match.points == 0


def test_r005_high_risk_merchant_category(rule_engine):
    tx_crypto = {
        "transaction_id": "TXN-CRYPTO",
        "customer_id": "C-4",
        "amount": 1000.0,
        "currency": "INR",
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Crypto",
        "customer_avg_amount": 1000.0,
        "timestamp": "2026-10-02 12:00:00",
    }
    outcomes = rule_engine.evaluate_transaction(tx_crypto)
    r005 = next(o for o in outcomes if o.rule_id == "R005")
    assert r005.triggered is True
    assert r005.points == 15
