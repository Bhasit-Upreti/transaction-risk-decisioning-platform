"""
Data Quality and Validation Observatory Page.
Monitors incoming data hygiene, rejected records, schema compliance, and validation failure causes.
"""

import streamlit as st
import pandas as pd
from src.database import get_db
from src.analytics import create_validation_error_chart
from config import (
    REQUIRED_FIELDS,
    ALLOWED_CURRENCIES,
    ALLOWED_COUNTRIES,
    ALLOWED_PAYMENT_METHODS,
    ALLOWED_MERCHANT_CATEGORIES,
)

st.set_page_config(page_title="Data Quality | Risk Platform", page_icon="🧹", layout="wide")

st.title("🧹 Data Quality & Validation Observatory")
st.markdown("Monitor ingestion hygiene, inspect malformed payloads, and isolate schema and boundary violations.")

db = get_db()
val_df = db.get_validation_failures()
tx_df = db.get_full_transactions()

total_valid = len(tx_df)
total_invalid = len(val_df)
total_received = total_valid + total_invalid
pass_rate = round((total_valid / total_received * 100), 2) if total_received > 0 else 0.0

# Summary Metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Ingested", f"{total_received:,}")
with col2:
    st.metric("Schema Compliant (Valid)", f"{total_valid:,}")
with col3:
    st.metric("Rejected (Data Defects)", f"{total_invalid:,}")
with col4:
    st.metric("Quality Pass Rate", f"{pass_rate}%", delta_color="normal" if pass_rate >= 85 else "inverse")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🚨 Rejected Records Log", "📊 Failure Analytics", "📖 Data Quality Schema & Rules"])

with tab1:
    st.subheader("Rejected Transaction Payloads")
    if val_df.empty:
        st.success("🎉 No validation failures recorded! All ingested transactions have passed quality checks.")
    else:
        st.markdown(f"**{len(val_df)} transaction payloads rejected before reaching the risk decisioning engine.**")

        # Download CSV button
        csv_data = val_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Rejected Records (CSV)",
            data=csv_data,
            file_name="rejected_transactions_audit.csv",
            mime="text/csv",
        )

        display_cols = ["id", "transaction_id", "error_count", "error_reasons", "source", "processed_at"]
        st.dataframe(val_df[display_cols], use_container_width=True, hide_index=True)

        st.markdown("##### 🔍 Inspect Rejected Raw Payload")
        selected_reject_id = st.selectbox(
            "Select Rejection ID to inspect raw incoming JSON:",
            val_df["id"].tolist()
        )
        if selected_reject_id:
            reject_row = val_df[val_df["id"] == selected_reject_id].iloc[0]
            st.error(f"**Reasons for Rejection:** {reject_row['error_reasons']}")
            st.code(reject_row["raw_payload"], language="json")

with tab2:
    st.subheader("Validation Error Root-Cause Breakdown")
    if val_df.empty:
        st.info("No failure data available to plot.")
    else:
        st.plotly_chart(create_validation_error_chart(val_df), use_container_width=True)

with tab3:
    st.subheader("Platform Data Quality Dictionary")
    st.markdown("""
    All incoming transaction records must strictly satisfy the following requirements before entering the business rules and risk scoring engines:
    """)

    schema_rules = [
        {"Field": "transaction_id", "Type": "String", "Constraint": "Required, Non-empty, Unique in batch & database"},
        {"Field": "customer_id", "Type": "String", "Constraint": "Required, Non-empty synthetic customer reference"},
        {"Field": "amount", "Type": "Numeric (Float)", "Constraint": "Required, Greater than zero (> 0.00)"},
        {"Field": "currency", "Type": "String (ISO)", f"Constraint": f"Must be in: {', '.join(ALLOWED_CURRENCIES)}"},
        {"Field": "timestamp", "Type": "ISO Datetime", "Constraint": "Required, Must be parseable datetime string"},
        {"Field": "country", "Type": "ISO Code", f"Constraint": f"Must be in: {', '.join(ALLOWED_COUNTRIES)}"},
        {"Field": "payment_method", "Type": "String", f"Constraint": f"Must be in: {', '.join(ALLOWED_PAYMENT_METHODS)}"},
        {"Field": "merchant_category", "Type": "String", f"Constraint": f"Must be in: {', '.join(ALLOWED_MERCHANT_CATEGORIES)}"},
        {"Field": "customer_avg_amount", "Type": "Numeric (Float)", "Constraint": "Optional, Non-negative (>= 0)"},
        {"Field": "customer_home_country", "Type": "ISO Code", "Constraint": "Optional, Customer default home country"},
    ]
    st.table(pd.DataFrame(schema_rules))
