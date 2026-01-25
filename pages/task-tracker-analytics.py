"""
Purpose:
    Historical analytics view for completed task performance.

What it does:
    - Enforces access control (permission-ready).
    - Loads ALL completed tasks from the partitioned CompletedTasks directory.
    - Provides filters (User, Task, Cadence, Date Range).
    - Computes KPI tiles and renders charts.
    - Optionally shows user-vs-team comparison table when a single user is selected.

Key utils used (inputs -> outputs):
    - utils.get_global_css() -> str
    - utils.get_user_context() -> UserContext
        Input: OS user + TasksAndTargets.xlsx user mapping + config.ALLOWED_ANALYTICS_USERS
        Output: user_login/full_name + can_view_analytics boolean
    - utils.load_all_completed_tasks(completed_dir: Path) -> DataFrame
        Input: config.COMPLETED_TASKS_DIR (partitioned parquet tree)
        Output: unified DataFrame with parsed timestamps + Date column

Primary inputs:
    - config.COMPLETED_TASKS_DIR
    - (Permission gate) config.ALLOWED_ANALYTICS_USERS

Primary outputs:
    - Streamlit UI (filters, KPIs, charts, comparison table)
"""

import streamlit as st
import pandas as pd
import altair as alt
import config
import utils

# Page configuration
st.set_page_config(page_title="Task Tracker - Analytics", layout="wide")

# Apply global styling
st.markdown(utils.get_global_css(), unsafe_allow_html=True)

# Enforce access control for this page
user_ctx = utils.get_user_context()
if not user_ctx.can_view_analytics:
    st.error("You are not authorized to view this page.")
    st.stop()

# Paths and data
COMPLETED_TASKS_DIR = config.COMPLETED_TASKS_DIR

@st.cache_data(ttl=300)
def load_targets_placeholder() -> pd.DataFrame:
    """
    Placeholder for future targets data.
    Expected structure:
        TaskName | TargetSeconds
    """
    return pd.DataFrame({"TaskName": [], "TargetSeconds": []})

# Load all completed tasks data
df = utils.load_all_completed_tasks(COMPLETED_TASKS_DIR)
if df.empty:
    st.warning("No completed task data available.")
    st.stop()
targets_df = load_targets_placeholder()

# Normalize partially complete flag
if "PartiallyComplete" not in df.columns:
    df["PartiallyComplete"] = False
else:
    df["PartiallyComplete"] = df["PartiallyComplete"].fillna(False).astype(bool)

def format_duration(seconds: float) -> str:
    """
    Format duration based on magnitude:
    - < 90 sec  -> seconds
    - < 60 min  -> minutes
    - >= 60 min -> hours
    """
    if pd.isna(seconds):
        return "—"
    seconds = float(seconds)
    if seconds < 90:
        return f"{int(seconds)} sec"
    elif seconds < 3600:
        return f"{round(seconds / 60, 1)} min"
    else:
        return f"{round(seconds / 3600, 2)} hr"

# Filters
st.subheader("Filters", anchor=False)
c1, c2, c3, c4 = st.columns(4)
with c1:
    user_filter = st.selectbox("User", options=["All"] + sorted(df["FullName"].dropna().unique().tolist()))
with c2:
    task_filter = st.multiselect("Task", options=sorted(df["TaskName"].unique().tolist()), default=[])
with c3:
    cadence_filter = st.multiselect("Cadence", options=sorted(df["TaskCadence"].dropna().unique().tolist()), default=[])
with c4:
    date_range = st.date_input("Date Range", value=(df["Date"].min(), df["Date"].max()))

# Apply filters
filtered_df = df.copy()
if user_filter != "All":
    filtered_df = filtered_df[filtered_df["FullName"] == user_filter]
if task_filter:
    filtered_df = filtered_df[filtered_df["TaskName"].isin(task_filter)]
if cadence_filter:
    filtered_df = filtered_df[filtered_df["TaskCadence"].isin(cadence_filter)]
if isinstance(date_range, tuple):
    start_date, end_date = (date_range[0], date_range[1]) if len(date_range) == 2 else (date_range[0], date_range[0])
else:
    start_date = end_date = date_range
if start_date and end_date:
    filtered_df = filtered_df[(filtered_df["Date"] >= start_date) & (filtered_df["Date"] <= end_date)]

# If no data after filtering, inform user
if filtered_df.empty:
    st.info("No data for selected filters.")
else:
    # Summary KPIs
    total_tasks = len(filtered_df)
    total_time = filtered_df["DurationSeconds"].sum()
    avg_time = filtered_df["DurationSeconds"].mean()
    # Layout for KPIs
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{total_tasks}</div><div class="kpi-label">Tasks</div></div>', unsafe_allow_html=True)
    with kpi2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{format_duration(total_time)}</div><div class="kpi-label">Total Time</div></div>', unsafe_allow_html=True)
    with kpi3:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{format_duration(avg_time)}</div><div class="kpi-label">Avg Time/Task</div></div>', unsafe_allow_html=True)
    st.divider()
    # Prepare data for charts
    # Time series of tasks per day
    time_df = filtered_df.groupby("Date", as_index=False).size().rename(columns={"size": "Tasks"})
    chart = alt.Chart(time_df).mark_line(point=True).encode(
        x="Date:T",
        y="Tasks:Q",
        tooltip=["Date", "Tasks"]
    ).properties(title="Tasks per Day")
    time_df["Date"] = pd.to_datetime(time_df["Date"], errors="coerce").dt.date
    st.altair_chart(chart, use_container_width=True)
    # Task distribution by cadence and top tasks by hours
    left, right = st.columns(2)
    with left:
        cad_df = filtered_df.groupby("TaskCadence", as_index=False)["DurationSeconds"].sum()
        cad_df["Hours"] = (cad_df["DurationSeconds"] / 3600).round(2)
        chart = alt.Chart(cad_df).mark_bar().encode(
            x=alt.X("TaskCadence:N", title="Cadence"),
            y=alt.Y("Hours:Q", title="Total Hours"),
            tooltip=["TaskCadence", "Hours"]
        ).properties(title="Total Hours by Cadence")
        st.altair_chart(chart, use_container_width=True)
    with right:
        task_df = filtered_df.groupby("TaskName", as_index=False)["DurationSeconds"].sum().nlargest(10, "DurationSeconds")
        task_df["Hours"] = (task_df["DurationSeconds"] / 3600).round(2)
        task_chart = alt.Chart(task_df).mark_bar().encode(
            x=alt.X("TaskName:N", title="Task", sort="-y"),
            y=alt.Y("Hours:Q", title="Total Hours"),
            tooltip=["TaskName", "Hours"]
        ).properties(title="Top 10 Tasks by Total Hours")
        st.altair_chart(task_chart, use_container_width=True)
    st.divider()
    # Comparison table for selected user (if filtered by a specific user)
    if user_filter != "All":
        st.subheader(f"Performance of {user_filter}", anchor=False)
        team_df = filtered_df.copy()
        selected_user = team_df[team_df["FullName"] == user_filter]
        others = team_df[team_df["FullName"] != user_filter]
        total_user_time = selected_user["DurationSeconds"].sum()
        total_team_time = team_df["DurationSeconds"].sum()
        target_time = 0
        # (Target time could be pulled from targets_df in future)
        comp_data = {
            "": ["Selected User", "Target (Goal)", "Team Average"],
            "Total Hours": [
                round(total_user_time / 3600, 2),
                round(target_time / 3600, 2) if target_time else "—",
                round((total_team_time / max(len(others), 1)) / 3600, 2) if not others.empty else "—",
            ],
        }
        comp_df = pd.DataFrame(comp_data)
        st.dataframe(comp_df, hide_index=True, width="stretch")
