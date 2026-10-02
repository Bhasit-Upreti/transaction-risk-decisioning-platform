"""
Transaction Risk Decisioning & Data Quality Platform
Main Entry Point and Executive Overview Dashboard.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from config import DATABASE_PATH
from src.database import get_db
from src.pipeline import TransactionPipeline
from src.generator import generate_synthetic_transactions
from src.ingestion import ingest_csv
from src.analytics import (
    compute_summary_metrics,
    create_decision_distribution_chart,
    create_risk_score_histogram,
    create_rule_trigger_bar_chart,
    create_volume_timeline_chart,
)

# Page Configuration
st.set_page_config(
    page_title="Transaction Risk & Data Quality Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Modern Fintech Dashboard Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .badge-approve {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .badge-review {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .badge-decline {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Database and Pipeline
db = get_db()
pipeline = TransactionPipeline(db=db)

# Sidebar: Controls & Ingestion Center
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shield-check.png", width=64)
    st.title("Risk Ops Center")
    st.caption("v1.0.0 | Synthetic Risk Simulation")

    st.markdown("---")
    st.subheader("📥 Ingestion Controls")

    ingest_mode = st.radio(
        "Ingestion Source:",
        ["Synthetic Generator", "Upload CSV", "Load Demo Sample"],
        help="Choose how to feed transactions into the risk decisioning engine."
    )

    if ingest_mode == "Synthetic Generator":
        st.markdown("##### Generator Parameters")
        n_tx = st.slider(
            "Transaction Count",
            min_value=10,
            max_value=200,
            value=50,
            step=10
        )
        inject_defects = st.checkbox(
            "Inject Data Quality Defects",
            value=True,
            help="Injects malformed records to demonstrate validation filtering."
        )
        defect_rate = (
            st.slider("Defect Ratio (%)", min_value=5, max_value=40, value=15, step=5) / 100.0
            if inject_defects else 0.0
        )

        if st.button(
            "🚀 Ingest & Process Batch",
            use_container_width=True,
            type="primary"
        ):
            with st.spinner("Generating and processing transactions..."):
                try:
                    # Generate a batch-specific ID to avoid duplicate transaction IDs.
                    batch_id = int(datetime.now().timestamp() * 1000)

                    raw_df = generate_synthetic_transactions(
                        n_records=n_tx,
                        include_invalid=inject_defects,
                        invalid_ratio=defect_rate,
                        seed=batch_id % 10000,
                        start_id=batch_id,
                    )

                    st.write(f"Generated records: {len(raw_df)}")

                    result = pipeline.process_transactions(raw_df)

                    st.write(
                        f"Valid: {result.get('valid_count', 'N/A')} | "
                        f"Rejected: {result.get('invalid_count', 'N/A')}"
                    )

                    if result.get("success"):
                        if result.get("valid_count", 0) > 0:
                            st.success(result.get("message", "Batch processed."))
                        else:
                            st.warning(
                                f"No valid transactions were added. "
                                f"{result.get('invalid_count', 0)} records were rejected. "
                                "Check the Data Quality page for rejection reasons."
                            )
                        st.rerun()
                    else:
                        st.error(result.get("message", "Batch processing failed."))

                except Exception as e:
                    st.error("Synthetic transaction ingestion failed.")
                    st.exception(e)

    st.markdown("---")
    st.subheader("⚙️ Database Management")
    if st.button("🗑️ Reset All Data", help="Clears SQLite database to starting state."):
        db.clear_all_data()
        st.warning("Database reset successfully.")
        st.rerun()

# Main Screen Header
st.markdown('<div class="main-header">🛡️ Transaction Risk Decisioning & Data Quality Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Educational prototype demonstrating transaction ingestion, schema validation, business rule evaluation, explainable risk scoring, and analyst review workflows.</div>', unsafe_allow_html=True)

# Fetch Current Data from SQLite
transactions_df = db.get_full_transactions()
val_failures_df = db.get_validation_failures()

# Calculate Summary Metrics
metrics = compute_summary_metrics(transactions_df, val_failures_df)

# Top KPI Metric Cards
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

with kpi1:
    st.metric(
        label="Total Received",
        value=f"{metrics['total_received']:,}",
        help="All transaction payloads received by ingestion."
    )
with kpi2:
    st.metric(
        label="Quality Pass Rate",
        value=f"{metrics['pass_rate']}%",
        delta=f"{metrics['valid_count']} valid / {metrics['invalid_count']} rejected",
        delta_color="normal" if metrics['pass_rate'] >= 80 else "inverse",
        help="Percentage of records passing schema and value constraints."
    )
with kpi3:
    st.metric(
        label="Auto-Approved",
        value=f"{metrics['approve_count']:,}",
        delta=f"{metrics['approval_rate']}%",
        delta_color="off",
        help="Transactions with score 0-29."
    )
with kpi4:
    st.metric(
        label="Manual Review",
        value=f"{metrics['review_count']:,}",
        delta=f"{metrics['review_rate']}%",
        delta_color="off",
        help="Transactions with score 30-69."
    )
with kpi5:
    st.metric(
        label="Declined",
        value=f"{metrics['decline_count']:,}",
        delta=f"{metrics['decline_rate']}%",
        delta_color="off",
        help="Transactions with score 70-100."
    )
with kpi6:
    st.metric(
        label="Pending Reviews",
        value=f"{metrics['pending_reviews']:,}",
        help="Transactions awaiting analyst outcome in Review Queue."
    )

st.markdown("---")

# Empty State Notice if no data exists yet
if transactions_df.empty and val_failures_df.empty:
    st.info("👋 **Welcome to the Platform!** No transactions are currently loaded. Use the left sidebar to generate synthetic transactions or load the demo sample.")
else:
    # Analytical Visualizations Row
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.plotly_chart(
            create_decision_distribution_chart(transactions_df),
            use_container_width=True
        )

    with col_chart2:
        st.plotly_chart(
            create_risk_score_histogram(transactions_df),
            use_container_width=True
        )

    col_chart3, col_chart4 = st.columns(2)

    with col_chart3:
        st.plotly_chart(
            create_rule_trigger_bar_chart(transactions_df),
            use_container_width=True
        )

    with col_chart4:
        st.plotly_chart(
            create_volume_timeline_chart(transactions_df),
            use_container_width=True
        )

    # Recent Transactions Table Preview
    st.markdown("### 📋 Recent Valid Transactions")
    preview_cols = [
        "transaction_id", "customer_id", "amount", "currency",
        "timestamp", "merchant_category", "country", "risk_score",
        "decision", "review_status"
    ]
    available_cols = [c for c in preview_cols if c in transactions_df.columns]

    st.dataframe(
        transactions_df[available_cols].head(15),
        use_container_width=True,
        hide_index=True,
    )

    st.caption("💡 Navigate to **Transaction Explorer** in the sidebar for granular filtering, or **Data Quality** to inspect validation rejections.")
