"""
Manual Review Queue Page.
Enables fraud and risk operations analysts to inspect queued cases,
evaluate context, and record definitive review decisions.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from src.database import get_db

st.set_page_config(page_title="Manual Review Queue | Risk Platform", page_icon="⚖️", layout="wide")

st.title("⚖️ Risk Operations Manual Review Queue")
st.markdown("Investigate transactions flagged for human assessment, cross-reference customer profile history, and log outcomes.")

db = get_db()

# Filter by Review Status
col_tab, _ = st.columns([2, 4])
with col_tab:
    status_filter = st.selectbox(
        "Queue Status Filter:",
        ["Pending", "All", "Approved", "Declined", "Escalated"],
        index=0,
    )

queue_df = db.get_review_queue(status_filter=status_filter)

# Metric Summary Cards
all_queue = db.get_review_queue(status_filter="All")
pending_count = int((all_queue["review_status"] == "Pending").sum()) if not all_queue.empty else 0
approved_count = int((all_queue["review_status"] == "Approved").sum()) if not all_queue.empty else 0
declined_count = int((all_queue["review_status"] == "Declined").sum()) if not all_queue.empty else 0
escalated_count = int((all_queue["review_status"] == "Escalated").sum()) if not all_queue.empty else 0

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("⏳ Pending Analyst Review", pending_count)
with m2:
    st.metric("✅ Overridden / Approved", approved_count)
with m3:
    st.metric("🚫 Confirmed Declined", declined_count)
with m4:
    st.metric("🚩 Escalated Cases", escalated_count)

st.markdown("---")

if queue_df.empty:
    st.success(f"🎉 No cases matching status '{status_filter}'! Queue is clean.")
    st.stop()

# Queue Table View
st.subheader(f"Cases in Queue ({len(queue_df)} items)")
table_cols = [
    "transaction_id", "customer_id", "amount", "currency",
    "timestamp", "merchant_category", "country", "risk_score",
    "decision", "review_status"
]
available_cols = [c for c in table_cols if c in queue_df.columns]
st.dataframe(queue_df[available_cols], use_container_width=True, hide_index=True)

st.markdown("---")

# Case Investigation & Decision Form
st.subheader("📝 Case Review Dossier")

tx_options = queue_df["transaction_id"].tolist()
selected_tx = st.selectbox("Select Transaction to Review:", tx_options)

if selected_tx:
    case = db.get_transaction_details(selected_tx)
    if case:
        score = case.get("risk_score", 0)
        sys_dec = case.get("decision", "Unknown")

        # Header Info Card
        st.markdown(f"""
        <div style="background-color: #F1F5F9; border-left: 6px solid #3B82F6; padding: 14px 18px; border-radius: 6px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="margin: 0; color: #1E293B;">Case: {case['transaction_id']} (Customer: {case['customer_id']})</h3>
                    <div style="color: #64748B; margin-top: 4px;">Timestamp: {case['timestamp']} | Channel: {case['payment_method']} | Category: {case['merchant_category']}</div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 1.4rem; font-weight: 700; color: #1E293B;">Risk Score: {score}/100</span>
                    <div style="font-weight: 600; color: #D97706;">Initial System Decision: {sys_dec}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            st.markdown("##### 🔍 Comparative Behavioral Profile")
            amt = float(case["amount"])
            cust_avg = float(case.get("customer_avg_amount", amt))
            diff_ratio = (amt / cust_avg) if cust_avg > 0 else 1.0

            st.write(f"• **Transaction Amount:** {case['currency']} {amt:,.2f}")
            st.write(f"• **Customer Historical Average:** ₹{cust_avg:,.2f}")
            st.write(f"• **Relative Spike:** `{diff_ratio:.2f}x` average")

            txn_country = case["country"]
            home_country = case.get("customer_home_country", "Unknown")
            is_cross = txn_country != home_country
            st.write(f"• **Origin Country:** `{txn_country}`")
            st.write(f"• **Registered Home Country:** `{home_country}`")
            st.write(f"• **Cross-Border Mismatch:** {'⚠️ Yes (Cross-border)' if is_cross else '✅ No (Domestic)'}")

        with col_c2:
            st.markdown("##### 💡 System Decision & Triggered Rules")
            st.info(f"**Policy Reason:**\n{case.get('decision_explanation', 'No details available.')}")
            rules = case.get("rule_evaluations", [])
            triggered_rules = [r for r in rules if r["triggered"]]
            if triggered_rules:
                st.markdown("**Triggered Rules:**")
                for tr in triggered_rules:
                    st.write(f"• **{tr['rule_id']} - {tr['rule_name']}** (+{tr['points']} pts): {tr['reason']}")
            else:
                st.write("• No specific rules triggered.")

        st.markdown("---")

        # Analyst Review Form
        st.markdown("##### ✍️ Record Analyst Determination")
        with st.form(key=f"review_form_{selected_tx}"):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                reviewer_name = st.text_input("Reviewer Name / ID", value="Risk Analyst Alice")
                outcome_selection = st.selectbox(
                    "Review Determination:",
                    [
                        "Approved (False Positive / Customer Verified)",
                        "Declined (Confirmed Suspicious / Fraud Risk)",
                        "Escalated (Requires Compliance / Law Enforcement Audit)",
                    ]
                )
            with f_col2:
                notes = st.text_area(
                    "Analyst Notes & Rationale",
                    placeholder="Document verification steps (e.g. contacted customer, card re-auth, travel notice confirmation)...",
                    height=100
                )

            submit_review = st.form_submit_button("💾 Save Review Determination", type="primary", use_container_width=True)

            if submit_review:
                if "Approved" in outcome_selection:
                    final_status = "Approved"
                elif "Declined" in outcome_selection:
                    final_status = "Declined"
                else:
                    final_status = "Escalated"

                success = db.record_review(
                    transaction_id=selected_tx,
                    review_status=final_status,
                    reviewer_outcome=outcome_selection,
                    review_note=notes if notes else "Reviewed and confirmed by analyst.",
                    reviewer_name=reviewer_name,
                )
                if success:
                    st.success(f"Case {selected_tx} updated to status '{final_status}'!")
                    st.rerun()
                else:
                    st.error("Failed to update review record.")

# Completed Audit Trail
st.markdown("---")
st.subheader("📜 Recent Analyst Review Audit Trail")
reviewed_cases = all_queue[all_queue["review_status"] != "Pending"]
if not reviewed_cases.empty:
    st.dataframe(
        reviewed_cases[[
            "transaction_id", "customer_id", "amount", "decision",
            "review_status", "reviewer_outcome", "reviewer_name", "reviewed_at"
        ]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption("No manual reviews have been completed yet.")
