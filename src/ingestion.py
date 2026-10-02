"""
Transaction Ingestion Module.
Handles CSV file loading, standardization, and initial structure verification.
"""

from typing import Union, Tuple, Optional
import io
import pandas as pd


def ingest_csv(
    file_or_path: Union[str, io.BytesIO, io.StringIO],
    source_label: str = "csv_upload"
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Ingests and standardizes a transaction CSV file.

    Args:
        file_or_path: Path to CSV or a file-like buffer (e.g. Streamlit UploadedFile).
        source_label: Label indicating the origin of the data ('csv_upload', 'generator', etc.)

    Returns:
        Tuple of (DataFrame, error_message). If successful, error_message is None.
    """
    try:
        if isinstance(file_or_path, (io.BytesIO, io.StringIO)):
            df = pd.read_csv(file_or_path)
        else:
            df = pd.read_csv(str(file_or_path))

        if df.empty:
            return None, "The uploaded file is empty. Please provide a CSV with transaction records."

        # Standardize column headers: strip whitespace
        df.columns = [str(col).strip() for col in df.columns]

        # Case-insensitive mapping for essential columns if needed
        col_map = {col.lower(): col for col in df.columns}
        canonical_names = {
            "transaction_id": ["transaction_id", "tx_id", "transactionid", "id"],
            "customer_id": ["customer_id", "cust_id", "customerid"],
            "amount": ["amount", "txn_amount", "transaction_amount", "amt"],
            "currency": ["currency", "curr"],
            "timestamp": ["timestamp", "date", "datetime", "txn_time"],
            "merchant_category": ["merchant_category", "category", "merchant_cat"],
            "country": ["country", "txn_country"],
            "payment_method": ["payment_method", "payment_type", "method"],
            "customer_avg_amount": ["customer_avg_amount", "cust_avg_amount", "avg_amount"],
            "customer_home_country": ["customer_home_country", "home_country", "cust_country"],
        }

        rename_dict = {}
        for canonical, aliases in canonical_names.items():
            if canonical not in df.columns:
                for alias in aliases:
                    if alias in col_map:
                        rename_dict[col_map[alias]] = canonical
                        break

        if rename_dict:
            df = df.rename(columns=rename_dict)

        # Ensure 'source' column is populated
        if "source" not in df.columns:
            df["source"] = source_label
        else:
            df["source"] = df["source"].fillna(source_label)

        # Convert strings properly and strip spaces
        for str_col in ["transaction_id", "customer_id", "currency", "country", "merchant_category", "payment_method"]:
            if str_col in df.columns:
                df[str_col] = df[str_col].astype(str).str.strip()

        return df, None

    except pd.errors.EmptyDataError:
        return None, "The CSV file contains no data."
    except Exception as e:
        return None, f"Failed to parse CSV file: {str(e)}"
