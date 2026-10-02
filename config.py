"""
Configuration module for Transaction Risk Decisioning & Data Quality Platform.
Centralizes business rule parameters, scoring thresholds, decision bands,
allowed reference values, and storage settings.
"""

from pathlib import Path
from typing import Dict, Any, List

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "risk_platform.db"

# Data Quality & Validation Configuration
REQUIRED_FIELDS: List[str] = [
    "transaction_id",
    "customer_id",
    "amount",
    "currency",
    "timestamp",
    "merchant_category",
    "country",
    "payment_method",
]

ALLOWED_CURRENCIES: List[str] = [
    "INR", "USD", "EUR", "GBP", "CAD", "AUD", "SGD", "AED", "JPY"
]

ALLOWED_COUNTRIES: List[str] = [
    "IN", "US", "GB", "SG", "AE", "CA", "AU", "DE", "FR", "JP"
]

ALLOWED_PAYMENT_METHODS: List[str] = [
    "Card", "UPI", "Bank Transfer", "Wallet", "Net Banking"
]

ALLOWED_MERCHANT_CATEGORIES: List[str] = [
    "Electronics",
    "Grocery",
    "Travel",
    "Entertainment",
    "Retail",
    "Dining",
    "Gambling",
    "Crypto",
    "Healthcare",
    "Utilities"
]

# Business Rule Configuration
RULE_VERSION = "v1.0.0"

RULES_CONFIG: Dict[str, Dict[str, Any]] = {
    "R001": {
        "rule_id": "R001",
        "name": "High-Value Amount",
        "description": "Transaction amount exceeds the high-value threshold.",
        "points": 30,
        "enabled": True,
        "parameters": {
            "amount_threshold": 15000.0  # INR or base unit
        }
    },
    "R002": {
        "rule_id": "R002",
        "name": "Unusual Spike vs Customer Average",
        "description": "Amount is substantially higher than the customer historical average.",
        "points": 25,
        "enabled": True,
        "parameters": {
            "multiplier": 3.0,
            "min_excess_amount": 2000.0  # Avoid triggering on small micro-amounts (e.g. avg 10 vs 35)
        }
    },
    "R003": {
        "rule_id": "R003",
        "name": "Rapid Velocity (Repeated Transactions)",
        "description": "Customer initiated multiple transactions within a short time window.",
        "points": 25,
        "enabled": True,
        "parameters": {
            "window_minutes": 30,
            "count_threshold": 3  # >= 3 transactions in window triggers rule
        }
    },
    "R004": {
        "rule_id": "R004",
        "name": "Country Mismatch (Cross-Border)",
        "description": "Transaction origin country differs from the synthetic customer home country.",
        "points": 20,
        "enabled": True,
        "parameters": {}
    },
    "R005": {
        "rule_id": "R005",
        "name": "High-Risk Merchant Category",
        "description": "Merchant operates in a category prone to high chargeback or risk (e.g., Crypto, Gambling).",
        "points": 15,
        "enabled": True,
        "parameters": {
            "high_risk_categories": ["Crypto", "Gambling"]
        }
    }
}

# Decision Scoring Bands
# Score is bounded [0, 100]
DECISION_BANDS: Dict[str, Dict[str, Any]] = {
    "APPROVE": {
        "min_score": 0,
        "max_score": 29,
        "label": "Approve",
        "action": "Low risk; automated approval granted."
    },
    "REVIEW": {
        "min_score": 30,
        "max_score": 69,
        "label": "Review",
        "action": "Medium risk; queued for manual analyst review."
    },
    "DECLINE": {
        "min_score": 70,
        "max_score": 100,
        "label": "Decline",
        "action": "High risk; illustrative decline or restricted approval."
    }
}

# Default App Settings
DEFAULT_DECISION = "Review"
MAX_RISK_SCORE = 100
MIN_RISK_SCORE = 0
