"""
Transaction Explorer Page.
Allows analysts to search, filter, and inspect transaction decision explanations
and granular rule evaluation outcomes.
"""

import streamlit as st
import pandas as pd
from src.database import get_db

st.set_page_config(page_title="Transaction Explorer | Risk Platform", page_icon="🔍", layout="wide")

st.title("🔍 Transaction Explorer & Audit Inspector")
st.markdown("Inspect transaction decision records, rule triggering conditions, and customer historical context.")

db = get_db()
df = db.get_full_transactions()

if df.empty:
    st.info("No transaction data available. Please generate or ingest transactions on the main Overview page first.")
    st.stop()

# Filter Controls Section
st.subheader("Filter & Search")
col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    search_query = st.text_input("Search ID", placeholder="e.g. TXN-10001 or CUST-1005").strip().lower()

with col_f2:
    decision_options = ["All"] + sorted(df["decision"].dropna().unique().tolist())
    selected_decision = st.selectbox("Decision Filter", decision_options)

with col_f3:
    categories = ["All"] + sorted(df["merchant_category"].dropna().unique().tolist())
    selected_cat = st.selectbox("Merchant Category", categories)

with col_f4:
    review_statuses = ["All"] + sorted(df["review_status"].dropna().unique().tolist())
    selected_review = st.selectbox("Review Status", review_statuses)

score_min, score_max = st.slider(
    "Risk Score Range",
    min_value=0,
    max_value=100,
    value=(0, 100),
    help="Filter transactions by illustrative risk score bounds."
)

# Apply Filters
filtered_df = df.copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df["transaction_id"].str.lower().str.contains(search_query, na=False) |
        filtered_df["customer_id"].str.lower().str.contains(search_query, na=False)
    ]

if selected_decision != "All":
    filtered_df = filtered_df[filtered_df["decision"] == selected_decision]

if selected_cat != "All":
    filtered_df = filtered_df[filtered_df["merchant_category"] == selected_cat]

if selected_review != "All":
    filtered_df = filtered_df[filtered_df["review_status"] == selected_review]

filtered_df = filtered_df[
    (filtered_df["risk_score"] >= score_min) & (filtered_df["risk_score"] <= score_max)
]

st.markdown(f"**Showing {len(filtered_df)} of {len(df)} transactions**")

# Display Filtered Table
display_cols = [
    "transaction_id", "customer_id", "amount", "currency", "timestamp",
    "merchant_category", "country", "risk_score", "decision", "review_status"
]
st.dataframe(
    filtered_df[display_cols],
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")

# Granular Transaction Deep-Dive Inspector
st.subheader("🔬 Transaction Deep-Dive Inspector")

if not filtered_df.empty:
    tx_list = filtered_df["transaction_id"].tolist()
    default_tx = tx_list[0]
    selected_tx_id = st.selectbox("Select Transaction to Inspect in Detail:", tx_list)
else:
    selected_tx_id = None

if selected_tx_id:
    details = db.get_transaction_details(selected_tx_id)
    if details:
        # Decision Banner
        decision = details.get("decision", "Unknown")
        score = details.get("risk_score", 0)

        badge_color = {
            "Approve": "#10B981",
            "Review": "#F59E0B",
            "Decline": "#EF4444"
        }.get(decision, "#64748B")

        st.markdown(f"""
        <div style="background-color: {badge_color}15; border-left: 5px solid {badge_color}; padding: 12px 18px; border-radius: 4px; margin-bottom: 16px;">
            <span style="font-size: 1.3rem; font-weight: 700; color: {badge_color};">
                Decision: {decision.upper()}
            </span>
            <span style="font-size: 1.1rem; margin-left: 20px; color: #334155;">
                Risk Score: <strong>{score}/100</strong>
            </span>
            <div style="color: #475569; margin-top: 6px;">
                {details.get("action_note", "")}
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            st.markdown("##### 💳 Transaction Data")
            st.write(f"**Transaction ID:** `{details['transaction_id']}`")
            st.write(f"**Customer ID:** `{details['customer_id']}`")
            st.write(f"**Amount:** {details['currency']} {float(details['amount']):,.2f}")
            st.write(f"**Timestamp:** {details['timestamp']}")
            st.write(f"**Payment Method:** {details['payment_method']}")
            st.write(f"**Source:** `{details.get('source', 'unknown')}`")

        with col_d2:
            st.markdown("##### 👤 Customer Profile Context")
            st.write(f"**Category:** {details['merchant_category']}")
            st.write(f"**Txn Country:** `{details['country']}`")
            st.write(f"**Home Country:** `{details.get('customer_home_country', 'N/A')}`")
            cust_avg = float(details.get("customer_avg_amount", 0.0))
            st.write(f"**Customer Historical Avg:** ₹{cust_avg:,.2f}")
            ratio = (float(details['amount']) / cust_avg) if cust_avg > 0 else 1.0
            st.write(f"**Current Amount Ratio:** `{ratio:.2f}x` average")

        with col_d3:
            st.markdown("##### ⚖️ Review Status")
            rev_status = details.get("review_status", "None")
            st.write(f"**Status:** `{rev_status}`")
            st.write(f"**Reviewer:** {details.get('reviewer_name') or 'N/A'}")
            st.write(f"**Outcome:** {details.get('reviewer_outcome') or 'Pending'}")
            st.write(f"**Analyst Note:** {details.get('review_note') or 'None'}")
            st.write(f"**Reviewed At:** {details.get('reviewed_at') or 'N/A'}")

        # Decision Explanation
        st.markdown("##### 💡 Decision Explanation")
        st.info(details.get("decision_explanation", "No explanation recorded."))

        # Granular Rule Breakdown Table
        st.markdown("##### 📜 Evaluated Business Rules Breakdown")
        rule_evals = details.get("rule_evaluations", [])
        if rule_evals:
            eval_rows = []
            for r in rule_evals:
                eval_rows.append({
                    "Rule ID": r["rule_id"],
                    "Rule Name": r["rule_name"],
                    "Status": "🚨 TRIGGERED" if r["triggered"] else "✅ Passed",
                    "Points Awarded": r["points"],
                    "Condition / Threshold": r["threshold_info"],
                    "Reason Detail": r["reason"],
                })
            st.dataframe(pd.DataFrame(eval_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No granular rule breakdown logs available for this transaction.")
