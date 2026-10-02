"""
Data Quality and Validation Module.
Checks completeness, types, value constraints, and uniqueness of transactions.
Separates valid records from rejected records and attaches clear error explanations.
"""

from typing import Tuple, List, Dict, Any, Optional, Set
import json
import pandas as pd
from config import (
    REQUIRED_FIELDS,
    ALLOWED_CURRENCIES,
    ALLOWED_COUNTRIES,
    ALLOWED_PAYMENT_METHODS,
    ALLOWED_MERCHANT_CATEGORIES,
)


class TransactionValidator:
    """Validates transaction records against data quality and schema requirements."""

    def __init__(
        self,
        required_fields: Optional[List[str]] = None,
        allowed_currencies: Optional[List[str]] = None,
        allowed_countries: Optional[List[str]] = None,
        allowed_payment_methods: Optional[List[str]] = None,
        allowed_merchant_categories: Optional[List[str]] = None,
    ):
        self.required_fields = required_fields or REQUIRED_FIELDS
        self.allowed_currencies = set(allowed_currencies or ALLOWED_CURRENCIES)
        self.allowed_countries = set(allowed_countries or ALLOWED_COUNTRIES)
        self.allowed_payment_methods = set(allowed_payment_methods or ALLOWED_PAYMENT_METHODS)
        self.allowed_merchant_categories = set(allowed_merchant_categories or ALLOWED_MERCHANT_CATEGORIES)

    def validate_batch(
        self,
        df: pd.DataFrame,
        existing_tx_ids: Optional[Set[str]] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        Validates an incoming batch of transactions.

        Args:
            df: Raw DataFrame of transactions.
            existing_tx_ids: Optional set of transaction IDs already stored in SQLite.

        Returns:
            Tuple of:
                - valid_df: DataFrame of compliant records ready for business rules
                - invalid_df: DataFrame of rejected records with explicit error reasons
                - summary: Summary statistics dictionary
        """
        if df.empty:
            empty_valid = pd.DataFrame()
            empty_invalid = pd.DataFrame(columns=["transaction_id", "is_valid", "error_reasons", "raw_payload"])
            return empty_valid, empty_invalid, {
                "total": 0, "valid": 0, "invalid": 0, "pass_rate": 0.0, "errors_breakdown": {}
            }

        existing_ids = existing_tx_ids or set()
        seen_batch_ids: Set[str] = set()

        valid_rows: List[Dict[str, Any]] = []
        invalid_rows: List[Dict[str, Any]] = []
        error_counts: Dict[str, int] = {}

        # 1. Verify schema-level missing required columns
        missing_cols = [col for col in self.required_fields if col not in df.columns]

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            errors: List[str] = []

            # If entire columns are missing
            if missing_cols:
                for col in missing_cols:
                    errors.append(f"Missing required column '{col}'")

            # Check transaction_id
            tx_id_raw = row_dict.get("transaction_id")
            tx_id_str = str(tx_id_raw).strip() if tx_id_raw is not None and not pd.isna(tx_id_raw) else ""
            if not tx_id_str or tx_id_str.lower() in ("nan", "none", "null"):
                errors.append("Missing or empty transaction_id")
                clean_tx_id = f"UNKNOWN-ROW-{idx + 1}"
            else:
                clean_tx_id = tx_id_str
                # Duplicate check within batch
                if clean_tx_id in seen_batch_ids:
                    errors.append(f"Duplicate transaction_id '{clean_tx_id}' in batch")
                else:
                    seen_batch_ids.add(clean_tx_id)

                # Duplicate check against persistent storage
                if clean_tx_id in existing_ids:
                    errors.append(f"Duplicate transaction_id '{clean_tx_id}' already exists in database")

            # Check customer_id
            cust_id_raw = row_dict.get("customer_id")
            cust_id_str = str(cust_id_raw).strip() if cust_id_raw is not None and not pd.isna(cust_id_raw) else ""
            if not cust_id_str or cust_id_str.lower() in ("nan", "none", "null"):
                errors.append("Missing or empty customer_id")

            # Check amount
            amount_val = row_dict.get("amount")
            is_valid_amount = False
            parsed_amount = 0.0
            if amount_val is None or pd.isna(amount_val) or str(amount_val).strip() == "":
                errors.append("Missing amount")
            else:
                try:
                    parsed_amount = float(amount_val)
                    if parsed_amount <= 0:
                        errors.append("Amount must be greater than zero")
                    else:
                        is_valid_amount = True
                except (ValueError, TypeError):
                    errors.append(f"Amount must be a numeric value (received: '{amount_val}')")

            # Check timestamp
            ts_val = row_dict.get("timestamp")
            parsed_ts_str = ""
            if ts_val is None or pd.isna(ts_val) or str(ts_val).strip() == "":
                errors.append("Missing timestamp")
            else:
                try:
                    dt = pd.to_datetime(ts_val)
                    parsed_ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    errors.append(f"Invalid timestamp format (received: '{ts_val}')")

            # Check currency
            curr_val = row_dict.get("currency")
            curr_str = str(curr_val).strip().upper() if curr_val and not pd.isna(curr_val) else ""
            if not curr_str:
                errors.append("Missing currency")
            elif curr_str not in self.allowed_currencies:
                errors.append(f"Unrecognized or unsupported currency '{curr_str}'. Platform risk thresholds are INR-denominated.")

            # Check country
            country_val = row_dict.get("country")
            country_str = str(country_val).strip().upper() if country_val and not pd.isna(country_val) else ""
            if not country_str:
                errors.append("Missing country")
            elif country_str not in self.allowed_countries:
                errors.append(f"Unrecognized country '{country_str}'")

            # Check payment_method
            pm_val = row_dict.get("payment_method")
            pm_str = str(pm_val).strip() if pm_val and not pd.isna(pm_val) else ""
            if not pm_str:
                errors.append("Missing payment_method")
            elif pm_str not in self.allowed_payment_methods:
                errors.append(f"Unrecognized payment_method '{pm_str}'")

            # Check merchant_category
            mc_val = row_dict.get("merchant_category")
            mc_str = str(mc_val).strip() if mc_val and not pd.isna(mc_val) else ""
            if not mc_str:
                errors.append("Missing merchant_category")
            elif mc_str not in self.allowed_merchant_categories:
                errors.append(f"Unrecognized merchant_category '{mc_str}'")

            # Check optional historical fields if provided
            cust_avg_val = row_dict.get("customer_avg_amount")
            parsed_cust_avg = None
            if cust_avg_val is not None and not pd.isna(cust_avg_val) and str(cust_avg_val).strip() != "":
                try:
                    parsed_cust_avg = float(cust_avg_val)
                    if parsed_cust_avg < 0:
                        errors.append("customer_avg_amount cannot be negative")
                except (ValueError, TypeError):
                    errors.append(f"customer_avg_amount must be numeric (received: '{cust_avg_val}')")

            # If no errors: record is valid
            if not errors:
                valid_record = {
                    "transaction_id": clean_tx_id,
                    "customer_id": cust_id_str,
                    "amount": round(parsed_amount, 2),
                    "currency": curr_str,
                    "timestamp": parsed_ts_str,
                    "merchant_category": mc_str,
                    "country": country_str,
                    "payment_method": pm_str,
                    "customer_avg_amount": round(parsed_cust_avg, 2) if parsed_cust_avg is not None else None,
                    "customer_home_country": str(row_dict.get("customer_home_country", country_str)).strip().upper(),
                    "source": str(row_dict.get("source", "unknown")),
                }
                valid_rows.append(valid_record)
            else:
                # Record is invalid
                for err in errors:
                    error_counts[err] = error_counts.get(err, 0) + 1

                # Clean serializable payload for storage/inspection
                clean_payload = {}
                for k, v in row_dict.items():
                    clean_payload[k] = None if pd.isna(v) else str(v)

                invalid_rows.append({
                    "transaction_id": clean_tx_id,
                    "customer_id": cust_id_str if cust_id_str else "N/A",
                    "amount": amount_val if amount_val is not None and not pd.isna(amount_val) else "N/A",
                    "timestamp": ts_val if ts_val is not None and not pd.isna(ts_val) else "N/A",
                    "is_valid": False,
                    "error_count": len(errors),
                    "error_reasons": "; ".join(errors),
                    "raw_payload": json.dumps(clean_payload),
                    "source": str(row_dict.get("source", "unknown")),
                })

        valid_df = pd.DataFrame(valid_rows)
        invalid_df = pd.DataFrame(invalid_rows)

        total_count = len(df)
        valid_count = len(valid_df)
        invalid_count = len(invalid_df)
        pass_rate = round((valid_count / total_count * 100), 2) if total_count > 0 else 0.0

        summary = {
            "total": total_count,
            "valid": valid_count,
            "invalid": invalid_count,
            "pass_rate": pass_rate,
            "errors_breakdown": error_counts,
        }

        return valid_df, invalid_df, summary


def validate_transactions(
    df: pd.DataFrame,
    existing_tx_ids: Optional[Set[str]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Helper function to execute standard transaction validation."""
    validator = TransactionValidator()
    return validator.validate_batch(df, existing_tx_ids=existing_tx_ids)
