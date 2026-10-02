"""
Analytics and Visualization Module.
Prepares operational metrics and interactive Plotly charts for dashboard reporting.
"""

from typing import Dict, Any, List
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Custom palette for financial risk decisioning
COLOR_MAP = {
    "Approve": "#10B981",       # Green
    "Review": "#F59E0B",        # Amber
    "Decline": "#EF4444",       # Red
    "Auto-Approved": "#10B981",
    "Pending": "#3B82F6",       # Blue
    "Escalated": "#8B5CF6",     # Purple
    "Valid": "#10B981",
    "Invalid": "#EF4444",
}


def compute_summary_metrics(
    transactions_df: pd.DataFrame,
    validation_failures_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Calculates top-level KPI metrics across the platform."""
    valid_count = len(transactions_df) if not transactions_df.empty else 0
    invalid_count = len(validation_failures_df) if not validation_failures_df.empty else 0
    total_received = valid_count + invalid_count

    pass_rate = round((valid_count / total_received * 100), 1) if total_received > 0 else 0.0

    if not transactions_df.empty and "decision" in transactions_df.columns:
        decision_counts = transactions_df["decision"].value_counts().to_dict()
        approve_count = decision_counts.get("Approve", 0)
        review_count = decision_counts.get("Review", 0)
        decline_count = decision_counts.get("Decline", 0)

        approval_rate = round((approve_count / valid_count * 100), 1)
        review_rate = round((review_count / valid_count * 100), 1)
        decline_rate = round((decline_count / valid_count * 100), 1)

        avg_score = round(transactions_df["risk_score"].mean(), 1) if "risk_score" in transactions_df.columns else 0.0
        max_score = int(transactions_df["risk_score"].max()) if "risk_score" in transactions_df.columns else 0

        pending_reviews = 0
        if "review_status" in transactions_df.columns and "decision" in transactions_df.columns:
            pending_reviews = int(((transactions_df["decision"] == "Review") & (transactions_df["review_status"] == "Pending")).sum())
        elif "review_status" in transactions_df.columns:
            pending_reviews = int((transactions_df["review_status"] == "Pending").sum())
    else:
        approve_count = review_count = decline_count = 0
        approval_rate = review_rate = decline_rate = 0.0
        avg_score = max_score = 0
        pending_reviews = 0

    return {
        "total_received": total_received,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "pass_rate": pass_rate,
        "approve_count": approve_count,
        "review_count": review_count,
        "decline_count": decline_count,
        "approval_rate": approval_rate,
        "review_rate": review_rate,
        "decline_rate": decline_rate,
        "avg_risk_score": avg_score,
        "max_risk_score": max_score,
        "pending_reviews": pending_reviews,
    }


def create_decision_distribution_chart(df: pd.DataFrame) -> go.Figure:
    """Creates a donut chart of transaction decisions."""
    if df.empty or "decision" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="No Decisions Available")
        return fig

    counts = df["decision"].value_counts().reset_index()
    counts.columns = ["Decision", "Count"]

    colors = [COLOR_MAP.get(d, "#94A3B8") for d in counts["Decision"]]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts["Decision"],
                values=counts["Count"],
                hole=0.45,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="label+percent",
                hoverinfo="label+value+percent",
            )
        ]
    )
    fig.update_layout(
        title="Decisions Breakdown",
        showlegend=True,
        margin=dict(t=40, b=20, l=20, r=20),
        height=320,
    )
    return fig


def create_risk_score_histogram(df: pd.DataFrame) -> go.Figure:
    """Creates a distribution histogram of risk scores."""
    if df.empty or "risk_score" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="No Risk Scores Available")
        return fig

    fig = px.histogram(
        df,
        x="risk_score",
        nbins=20,
        color="decision",
        color_discrete_map=COLOR_MAP,
        labels={"risk_score": "Illustrative Risk Score (0-100)", "count": "Transactions"},
        title="Risk Score Distribution",
        barmode="overlay",
        opacity=0.8,
    )
    # Add vertical lines for decision thresholds
    fig.add_vline(x=30, line_width=2, line_dash="dash", line_color="#F59E0B", annotation_text="Review (30)")
    fig.add_vline(x=70, line_width=2, line_dash="dash", line_color="#EF4444", annotation_text="Decline (70)")

    fig.update_layout(
        xaxis_range=[0, 105],
        margin=dict(t=40, b=20, l=20, r=20),
        height=320,
        legend_title_text="Decision",
    )
    return fig


def create_rule_trigger_bar_chart(df: pd.DataFrame) -> go.Figure:
    """Extracts and counts individual triggered rules from triggered_rule_ids."""
    if df.empty or "triggered_rule_ids" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="No Rule Data")
        return fig

    rule_counts: Dict[str, int] = {}
    for rule_str in df["triggered_rule_ids"].dropna():
        if rule_str in ("None", ""):
            continue
        for r in str(rule_str).split(","):
            r_clean = r.strip()
            if r_clean and r_clean != "None":
                rule_counts[r_clean] = rule_counts.get(r_clean, 0) + 1

    if not rule_counts:
        fig = go.Figure()
        fig.update_layout(title="No Rules Triggered Yet")
        return fig

    rule_labels = {
        "R001": "R001: High Value",
        "R002": "R002: Spike vs Avg",
        "R003": "R003: Velocity Spike",
        "R004": "R004: Country Mismatch",
        "R005": "R005: High-Risk Category",
    }

    plot_data = pd.DataFrame([
        {"Rule": rule_labels.get(r, r), "Rule_ID": r, "Triggers": count}
        for r, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)
    ])

    fig = px.bar(
        plot_data,
        x="Triggers",
        y="Rule",
        orientation="h",
        text="Triggers",
        color="Triggers",
        color_continuous_scale="Purples",
        title="Rule Trigger Frequency",
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        margin=dict(t=40, b=20, l=20, r=20),
        height=320,
        showlegend=False,
    )
    return fig


def create_volume_timeline_chart(df: pd.DataFrame) -> go.Figure:
    """Creates a time series plot of transactions by timestamp."""
    if df.empty or "timestamp" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="No Timeline Data")
        return fig

    try:
        temp_df = df.copy()
        temp_df["dt"] = pd.to_datetime(temp_df["timestamp"])
        temp_df["hour_group"] = temp_df["dt"].dt.floor("h")

        grouped = temp_df.groupby(["hour_group", "decision"]).size().reset_index(name="Count")

        fig = px.bar(
            grouped,
            x="hour_group",
            y="Count",
            color="decision",
            color_discrete_map=COLOR_MAP,
            labels={"hour_group": "Time (Hourly)", "Count": "Transaction Count"},
            title="Transaction Volume Timeline",
        )
        fig.update_layout(
            margin=dict(t=40, b=20, l=20, r=20),
            height=320,
            xaxis_title="Timeline",
        )
        return fig
    except Exception:
        fig = go.Figure()
        fig.update_layout(title="Timeline formatting unavailable")
        return fig


def create_validation_error_chart(val_failures_df: pd.DataFrame) -> go.Figure:
    """Creates a chart of validation failure causes from rejected records."""
    if val_failures_df.empty or "error_reasons" not in val_failures_df.columns:
        fig = go.Figure()
        fig.update_layout(title="No Validation Failures Logged (100% Quality Pass)")
        return fig

    error_freq: Dict[str, int] = {}
    for err_str in val_failures_df["error_reasons"].dropna():
        for reason in str(err_str).split(";"):
            clean_reason = reason.strip()
            if clean_reason:
                error_freq[clean_reason] = error_freq.get(clean_reason, 0) + 1

    if not error_freq:
        fig = go.Figure()
        fig.update_layout(title="No Error Breakdown Available")
        return fig

    err_df = pd.DataFrame([
        {"Error": err, "Occurrences": count}
        for err, count in sorted(error_freq.items(), key=lambda x: x[1], reverse=True)
    ])

    fig = px.bar(
        err_df,
        x="Occurrences",
        y="Error",
        orientation="h",
        text="Occurrences",
        color="Occurrences",
        color_continuous_scale="Reds",
        title="Top Data Quality Rejection Reasons",
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        margin=dict(t=40, b=20, l=20, r=20),
        height=320,
        showlegend=False,
    )
    return fig
