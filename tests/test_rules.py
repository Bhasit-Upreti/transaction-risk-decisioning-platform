"""
Unit tests for business rule evaluation engine.
Verifies transparent logic and points assignment for each rule.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from src.rules import BusinessRuleEngine


@pytest.fixture
def rule_engine():
    return BusinessRuleEngine()


def test_r001_high_value_rule_trigger(rule_engine):
    # Above threshold (threshold is 15000)
    tx_high = {
        "transaction_id": "TXN-1",
        "customer_id": "C-1",
        "amount": 25000.0,
        "customer_avg_amount": 2000.0,
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "timestamp": "2026-10-02 12:00:00",
    }
    outcomes_high = rule_engine.evaluate_transaction(tx_high)
    r001 = next(o for o in outcomes_high if o.rule_id == "R001")
    assert r001.triggered is True
    assert r001.points == 30

    # Below threshold
    tx_low = tx_high.copy()
    tx_low["amount"] = 500.0
    outcomes_low = rule_engine.evaluate_transaction(tx_low)
    r001_low = next(o for o in outcomes_low if o.rule_id == "R001")
    assert r001_low.triggered is False
    assert r001_low.points == 0


def test_r002_spike_vs_customer_average(rule_engine):
    # Customer avg is 1000, multiplier is 3.0x -> amount 5000 is 5x, diff 4000 >= 2000
    tx_spike = {
        "transaction_id": "TXN-2",
        "customer_id": "C-2",
        "amount": 5000.0,
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

    # Normal amount: 1500 vs avg 1000
    tx_normal = tx_spike.copy()
    tx_normal["amount"] = 1500.0
    outcomes_normal = rule_engine.evaluate_transaction(tx_normal)
    r002_normal = next(o for o in outcomes_normal if o.rule_id == "R002")
    assert r002_normal.triggered is False
    assert r002_normal.points == 0


def test_r003_velocity_rule(rule_engine):
    base_time = datetime(2026, 10, 2, 14, 0, 0)
    cust_id = "C-VELOCITY"

    # Create 3 prior transactions for this customer within 10 minutes
    hist_records = [
        {
            "transaction_id": f"TXN-HIST-{i}",
            "customer_id": cust_id,
            "amount": 500.0,
            "timestamp": (base_time - timedelta(minutes=i * 2)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for i in range(1, 4)
    ]
    historical_df = pd.DataFrame(hist_records)

    current_tx = {
        "transaction_id": "TXN-CURRENT",
        "customer_id": cust_id,
        "amount": 800.0,
        "timestamp": base_time.strftime("%Y-%m-%d %H:%M:%S"),
        "country": "IN",
        "customer_home_country": "IN",
        "merchant_category": "Retail",
        "customer_avg_amount": 800.0,
    }

    outcomes = rule_engine.evaluate_transaction(current_tx, historical_context=historical_df)
    r003 = next(o for o in outcomes if o.rule_id == "R003")
    assert r003.triggered is True
    assert r003.points == 25


def test_r004_country_mismatch_rule(rule_engine):
    tx_mismatch = {
        "transaction_id": "TXN-CROSS",
        "customer_id": "C-3",
        "amount": 1000.0,
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

    # Matching country
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
