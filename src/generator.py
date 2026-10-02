"""
Synthetic Transaction Generator.
Produces realistic normal transactions, edge-case transactions (velocity spikes,
high amounts, cross-border), and optionally malformed records for testing data quality.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd

from config import (
    ALLOWED_CURRENCIES,
    ALLOWED_COUNTRIES,
    ALLOWED_PAYMENT_METHODS,
    ALLOWED_MERCHANT_CATEGORIES,
)


class SyntheticTransactionGenerator:
    """Generates synthetic financial transaction streams and batches."""

    def __init__(self, seed: Optional[int] = 42):
        if seed is not None:
            random.seed(seed)
        self.customers: Dict[str, Dict[str, Any]] = self._init_customer_profiles()

    def _init_customer_profiles(self, count: int = 50) -> Dict[str, Dict[str, Any]]:
        """Pre-generate a pool of customer profiles with typical habits."""
        profiles = {}
        for i in range(1, count + 1):
            cust_id = f"CUST-{1000 + i}"
            home_country = random.choice(["IN", "IN", "IN", "US", "GB", "SG", "AE"])
            typical_avg = round(random.uniform(400, 3500), 2)
            preferred_category = random.choice(
                ["Grocery", "Dining", "Retail", "Utilities", "Electronics"]
            )
            profiles[cust_id] = {
                "customer_id": cust_id,
                "home_country": home_country,
                "avg_amount": typical_avg,
                "preferred_category": preferred_category,
            }
        return profiles

    def generate_batch(
        self,
        n_records: int = 50,
        start_id: int = 10001,
        base_time: Optional[datetime] = None,
        include_invalid: bool = True,
        invalid_ratio: float = 0.10,
        seed: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Generate a batch of synthetic transactions.

        Args:
            n_records: Total number of records to produce.
            start_id: Starting integer for transaction IDs (TXN-XXXXX).
            base_time: Anchor datetime for timestamps (defaults to current local time).
            include_invalid: Whether to inject intentionally malformed records.
            invalid_ratio: Approximate fraction of records that are invalid (0.0 to 1.0).
            seed: Optional seed for reproducibility.

        Returns:
            pd.DataFrame with transaction records.
        """
        if seed is not None:
            random.seed(seed)

        if base_time is None:
            base_time = datetime.now() - timedelta(hours=6)

        records: List[Dict[str, Any]] = []
        customer_ids = list(self.customers.keys())

        # Determine invalid record count
        n_invalid = int(n_records * invalid_ratio) if include_invalid else 0
        n_valid = n_records - n_invalid

        current_time = base_time

        # 1. Generate Valid Records
        for i in range(n_valid):
            tx_id = f"TXN-{start_id + i}"
            cust_id = random.choice(customer_ids)
            profile = self.customers[cust_id]

            # Advance time slightly (0-15 minutes)
            current_time += timedelta(minutes=random.randint(0, 15), seconds=random.randint(0, 59))

            # Scenario selection
            scenario_roll = random.random()
            if scenario_roll < 0.65:
                # Normal everyday transaction
                amount = round(max(50.0, random.gauss(profile["avg_amount"], profile["avg_amount"] * 0.3)), 2)
                country = profile["home_country"]
                merchant_cat = (
                    profile["preferred_category"]
                    if random.random() < 0.7
                    else random.choice(ALLOWED_MERCHANT_CATEGORIES)
                )
            elif scenario_roll < 0.80:
                # High-value transaction
                amount = round(random.uniform(16000, 75000), 2)
                country = profile["home_country"]
                merchant_cat = random.choice(["Electronics", "Travel", "Retail"])
            elif scenario_roll < 0.90:
                # Country mismatch (Cross-border)
                amount = round(max(100.0, random.gauss(profile["avg_amount"] * 1.5, profile["avg_amount"] * 0.5)), 2)
                other_countries = [c for c in ALLOWED_COUNTRIES if c != profile["home_country"]]
                country = random.choice(other_countries)
                merchant_cat = random.choice(["Travel", "Electronics", "Retail"])
            elif scenario_roll < 0.95:
                # Velocity spike (customer making immediate transaction)
                current_time -= timedelta(minutes=random.randint(1, 4))
                amount = round(random.uniform(1000, 12000), 2)
                country = profile["home_country"]
                merchant_cat = random.choice(ALLOWED_MERCHANT_CATEGORIES)
            else:
                # High-risk merchant category (Gambling or Crypto)
                amount = round(random.uniform(3000, 25000), 2)
                country = profile["home_country"]
                merchant_cat = random.choice(["Gambling", "Crypto"])

            records.append({
                "transaction_id": tx_id,
                "customer_id": cust_id,
                "amount": amount,
                "currency": "INR",
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "merchant_category": merchant_cat,
                "country": country,
                "payment_method": random.choice(ALLOWED_PAYMENT_METHODS),
                "customer_avg_amount": profile["avg_amount"],
                "customer_home_country": profile["home_country"],
                "source": "generator",
            })

        # 2. Inject Invalid Records if requested
        invalid_types = [
            "missing_customer_id",
            "negative_amount",
            "zero_amount",
            "non_numeric_amount",
            "invalid_timestamp",
            "duplicate_tx_id",
            "invalid_currency",
            "invalid_country",
        ]

        for j in range(n_invalid):
            idx = n_valid + j
            tx_id = f"TXN-{start_id + idx}"
            cust_id = random.choice(customer_ids)
            profile = self.customers[cust_id]
            inv_type = random.choice(invalid_types)

            rec = {
                "transaction_id": tx_id,
                "customer_id": cust_id,
                "amount": round(random.uniform(500, 5000), 2),
                "currency": "INR",
                "timestamp": (current_time + timedelta(minutes=j * 5)).strftime("%Y-%m-%d %H:%M:%S"),
                "merchant_category": "Retail",
                "country": profile["home_country"],
                "payment_method": "Card",
                "customer_avg_amount": profile["avg_amount"],
                "customer_home_country": profile["home_country"],
                "source": "generator",
            }

            if inv_type == "missing_customer_id":
                rec["customer_id"] = ""
            elif inv_type == "negative_amount":
                rec["amount"] = -round(random.uniform(100, 1500), 2)
            elif inv_type == "zero_amount":
                rec["amount"] = 0.0
            elif inv_type == "non_numeric_amount":
                rec["amount"] = "INVALID_AMT"
            elif inv_type == "invalid_timestamp":
                rec["timestamp"] = "not-a-valid-date"
            elif inv_type == "duplicate_tx_id" and len(records) > 0:
                # Reuse an already generated transaction_id
                rec["transaction_id"] = records[0]["transaction_id"]
            elif inv_type == "invalid_currency":
                rec["currency"] = "XYZ_BAD"
            elif inv_type == "invalid_country":
                rec["country"] = "ZZ_INVALID"

            records.append(rec)

        # Shuffle slightly so invalid records are mixed in naturally
        random.shuffle(records)
        df = pd.DataFrame(records)
        return df


def generate_synthetic_transactions(
    n_records: int = 50,
    include_invalid: bool = True,
    invalid_ratio: float = 0.10,
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """Convenience helper to generate synthetic transactions."""
    gen = SyntheticTransactionGenerator(seed=seed)
    return gen.generate_batch(
        n_records=n_records,
        include_invalid=include_invalid,
        invalid_ratio=invalid_ratio,
        seed=seed,
    )
