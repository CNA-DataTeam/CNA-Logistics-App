"""
analytics.py

Purpose:
    Task Tracker – Analytics & Performance View

    - Aggregates all completed task parquet outputs into a single dataframe
    - Provides slicers (User, Task, Cadence, Date)
    - Displays summary KPIs and visuals
    - Conditionally renders a comparison table for a selected user:
        * Selected User
        * Target (placeholder – Excel import later)
        * Team Average (excluding selected user)

Requirements:
    Same environment and config as app.py
"""

# ============================================================
# IMPORTS
# ============================================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import pyarrow.dataset as ds
import config
import altair as alt

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Task Tracker - Analytics",
    layout="wide",
)

# ============================================================
# GLOBAL STYLING (MATCH MAIN APP)
# ============================================================
@st.cache_data
def get_global_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600&family=Work+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Work Sans', sans-serif;
    }

    h1, h2, h3 {
        font-family: 'Poppins', sans-serif;
        font-weight: 600;
    }

    .kpi-card {
        background-color: #F7F7F7;
        padding: 18px;
        border-radius: 12px;
        text-align: center;
    }

    .kpi-value {
        font-size: 28px;
        font-weight: 600;
    }

    .kpi-label {
        color: #6b6b6b;
        font-size: 14px;
    }

    .stDataFrame thead th {
        font-weight: 800 !important;
    }
    </style>
    """

st.markdown(get_global_css(), unsafe_allow_html=True)

# ============================================================
# PATHS
# ============================================================
COMPLETED_TASKS_DIR = config.COMPLETED_TASKS_DIR
TASKS_XLSX = Path(config.TASKS_XLSX_NAME)

# ============================================================
# DATA LOADERS
# ============================================================
@st.cache_data(ttl=300)
def load_all_completed_tasks(base_dir: Path) -> pd.DataFrame:
    files = list(base_dir.glob("user=*/year=*/month=*/day=*/*.parquet"))
    if not files:
        return pd.DataFrame()

    dataset = ds.dataset(files, format="parquet")
    df = dataset.to_table().to_pandas()

    df["StartTimestampUTC"] = pd.to_datetime(df["StartTimestampUTC"], utc=True)
    df["EndTimestampUTC"] = pd.to_datetime(df["EndTimestampUTC"], utc=True)
    df["Date"] = df["StartTimestampUTC"].dt.date

    return df


@st.cache_data(ttl=3600)
def load_targets_placeholder() -> pd.DataFrame:
    """
    Placeholder for future Excel import.
    Expected structure:
        TaskName | TargetSeconds
    """
    return pd.DataFrame(
        {
            "TaskName": [],
            "TargetSeconds": [],
        }
    )

# ============================================================
# LOAD DATA
# ============================================================
df = load_all_completed_tasks(COMPLETED_TASKS_DIR)

if df.empty:
    st.warning("No completed task data available.")
    st.stop()

targets_df = load_targets_placeholder()

# ============================================================
# NORMALIZE PARTIALLY COMPLETE COLUMN
# ============================================================

if "PartiallyComplete" not in df.columns:
    df["PartiallyComplete"] = False
else:
    # Ensure clean boolean dtype
    df["PartiallyComplete"] = (
        df["PartiallyComplete"]
        .fillna(False)
        .astype(bool)
    )

def format_duration(seconds: float) -> str:
    """
    Format duration based on magnitude:
    - < 90 sec  -> seconds
    - < 60 min  -> minutes
    - >= 60 min -> hours
    """
    if pd.isna(seconds):
        return "—"

    if seconds < 90:
        return f"{int(seconds)} sec"
    elif seconds < 3600:
        return f"{round(seconds / 60, 1)} min"
    else:
        return f"{round(seconds / 3600, 2)} hr"

# ============================================================
# SLICERS (TOP OF PAGE)
# ============================================================
st.subheader("Filters", anchor=False)

c1, c2, c3, c4 = st.columns(4)

with c1:
    user_filter = st.selectbox(
        "User",
        options=["All"] + sorted(df["FullName"].dropna().unique().tolist()),

    )

with c2:
    task_filter = st.multiselect(
        "Task",
        options=sorted(df["TaskName"].unique().tolist()),
        default=[],
    )

with c3:
    cadence_filter = st.multiselect(
        "Cadence",
        options=sorted(df["TaskCadence"].dropna().unique().tolist()),
        default=[],
    )

with c4:
    date_range = st.date_input(
        "Date Range",
        value=(
            df["Date"].min(),
            df["Date"].max(),
        ),
    )

# ============================================================
# APPLY FILTERS
# ============================================================
filtered_df = df.copy()

if user_filter != "All":
    filtered_df = filtered_df[filtered_df["FullName"] == user_filter]

if task_filter:
    filtered_df = filtered_df[filtered_df["TaskName"].isin(task_filter)]

if cadence_filter:
    filtered_df = filtered_df[filtered_df["TaskCadence"].isin(cadence_filter)]

if isinstance(date_range, tuple):
    if len(date_range) == 2:
        start_date, end_date = date_range
    elif len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        # Defensive fallback (should never happen)
        start_date = end_date = None
else:
    start_date = end_date = date_range

if start_date is not None and end_date is not None:
    filtered_df = filtered_df[
        (filtered_df["Date"] >= start_date) &
        (filtered_df["Date"] <= end_date)
    ]

# ============================================================
# KPI SUMMARY
# ============================================================
st.divider()

k1, k2, k3, k4 = st.columns(4)

total_tasks = len(filtered_df)
avg_duration = filtered_df["DurationSeconds"].mean()
tasks_per_day = (
    filtered_df.groupby("Date").size().mean()
    if not filtered_df.empty else 0
)

with k1:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{total_tasks:,}</div>
            <div class="kpi-label">Tasks Completed</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k2:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{format_duration(avg_duration)}</div>
            <div class="kpi-label">Avg Completion Time</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{tasks_per_day:.1f}</div>
            <div class="kpi-label">Avg Tasks / Day</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k4:
    pct_partial = (
        filtered_df["PartiallyComplete"].mean() * 100
        if not filtered_df.empty else 0
    )
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{pct_partial:.1f}%</div>
            <div class="kpi-label">Partially Complete</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# VISUALS (SIDE-BY-SIDE)
# ------------------------------------------------------------

time_df = (
    filtered_df
    .groupby("Date")
    .agg(
        TasksCompleted=("TaskName", "count"),
        AvgDurationSeconds=("DurationSeconds", "mean"),
    )
    .reset_index()
)

st.divider()
st.subheader("Task Volume", anchor=False)

left, right = st.columns([1, 1])

with left:
    # --- keep your existing adaptive over-time aggregation + chart here ---
    # (the block that creates agg_df and then st.altair_chart(chart, ...))
    # IMPORTANT: do not change it, just indent it under this 'with left:'.

    time_df["Date"] = pd.to_datetime(time_df["Date"], errors="coerce").dt.date

    # Drop null dates (defensive)
    time_df = time_df.dropna(subset=["Date"])

    # If filters produce no rows, avoid min/max NaN recursion and show a clean message
    if time_df.empty:
        st.info("No data available for the selected filters/date range.")
        st.stop()

    min_date = time_df["Date"].min()
    max_date = time_df["Date"].max()
    day_span = (pd.to_datetime(max_date) - pd.to_datetime(min_date)).days + 1

    if day_span <= 30:
        time_df["Period"] = time_df["Date"]
        period_title = "Day"
    elif day_span <= 90:
        time_df["Period"] = (
            pd.to_datetime(time_df["Date"])
            .dt.to_period("W")
            .apply(lambda p: p.start_time)
        )
        period_title = "Week"
    else:
        time_df["Period"] = (
            pd.to_datetime(time_df["Date"])
            .dt.to_period("M")
            .apply(lambda p: p.start_time)
        )
        period_title = "Month"

    agg_df = (
        time_df
        .groupby("Period", as_index=False)
        .agg(
            TasksCompleted=("TasksCompleted", "sum"),
            AvgDurationSeconds=("AvgDurationSeconds", "mean"),
        )
    )

    agg_df["AvgDurationFormatted"] = agg_df["AvgDurationSeconds"].apply(format_duration)

    y_max = int(agg_df["TasksCompleted"].max()) if not agg_df.empty else 0

    chart = (
        alt.Chart(agg_df)
        .mark_bar()
        .encode(
            x=alt.X("Period:T", title=period_title, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("TasksCompleted:Q", title="Tasks Completed", scale=alt.Scale(domain=[0, y_max])), 

            tooltip=[
                alt.Tooltip("Period:T", title=period_title),
                alt.Tooltip("TasksCompleted:Q", title="Tasks Completed"),
                alt.Tooltip("AvgDurationFormatted:N", title="Avg Completion Time"),
            ],
        )
        .properties(height=350)
    )

    st.altair_chart(chart, use_container_width=True)

with right:
    # ------------------------------------------------------------
    # TASKS COMPLETED BY TASK NAME (TOP N)
    # ------------------------------------------------------------
    task_counts = (
        filtered_df
        .groupby("TaskName")
        .agg(
            TasksCompleted=("TaskName", "size"),
            AvgDurationSeconds=("DurationSeconds", "mean"),
        )
        .reset_index()
        .sort_values("TasksCompleted", ascending=False)
    )

    task_counts["AvgDurationFormatted"] = (
        task_counts["AvgDurationSeconds"].apply(format_duration)
    )
    top_n = 15
    task_counts_top = task_counts.head(top_n).copy()

    y_max_task = int(task_counts_top["TasksCompleted"].max()) if not task_counts_top.empty else 0

    task_chart = (
        alt.Chart(task_counts_top)
        .mark_bar()
        .encode(
            y=alt.Y(
                "TaskName:N",
                sort="-x",
                title=None,
                axis=alt.Axis(
                    labelLimit=260,
                    labelPadding=8,
                ),
            ),
            x=alt.X(
                "TasksCompleted:Q",
                title="Tasks Completed",
                scale=alt.Scale(domain=[0, y_max_task]),
                axis=alt.Axis(
                    values=list(range(0, y_max_task + 1)),
                    format="d",
                ),
            ),
            tooltip=[
                alt.Tooltip("TaskName:N", title="Task"),
                alt.Tooltip("TasksCompleted:Q", title="Tasks Completed"),
                alt.Tooltip("AvgDurationFormatted:N", title="Avg Completion Time"),
            ],
        )
        .properties(height=350, title=f"Top {top_n} Tasks")
    )

    st.altair_chart(task_chart, use_container_width=True)


# ============================================================
# USER COMPARISON TABLE (CONDITIONAL)
# ============================================================
if user_filter != "All":
    st.divider()
    st.subheader(f"Performance Breakdown – {user_filter}", anchor=False)

    user_df = df[df["FullName"] == user_filter]
    team_df = df[df["FullName"] != user_filter]

    user_summary = (
        user_df.groupby("TaskName")
        .size()
        .rename("User Tasks Completed")
    )

    team_summary = (
        team_df.groupby("TaskName")
        .size()
        .rename("Team Tasks Completed")
    )

    comparison_df = (
        pd.concat([user_summary, team_summary], axis=1)
        .fillna(0)
        .reset_index()
    )

    st.dataframe(
        comparison_df,
        hide_index=True,
        width="stretch",
    )

st.caption("Task Tracker – Analytics View")