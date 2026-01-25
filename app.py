# ============================================================
# IMPORTS
# ============================================================
import streamlit as st
import pandas as pd
import uuid
import config
from pathlib import Path
from functools import lru_cache
from streamlit_autorefresh import st_autorefresh

from task_tracker_utils import (
    EASTERN_TZ,
    build_out_dir,
    delete_live_activity,
    format_hh_mm_parts,
    format_hhmmss,
    format_time_ago,
    get_full_name_for_user,
    get_global_css,
    get_logo_base64,
    get_os_user,
    load_accounts,
    load_all_user_full_names,
    load_live_activities,
    load_own_live_activity,
    load_recent_tasks,
    load_tasks,
    now_utc,
    parse_hhmmss,
    sanitize_key,
    save_live_activity,
    to_eastern,
    update_live_activity_state,
)

# ============================================================
# APP CONFIG
# ============================================================
APP_VERSION = "1.8.1" 

st.set_page_config(
    page_title="Task Tracker",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Hide Streamlit header */
    header {visibility: hidden;}

    /* Hide Streamlit footer */
    footer {visibility: hidden;}

    /* Remove top padding caused by header */
    .block-container {
        padding-top: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# GLOBAL STYLING
# ============================================================
st.markdown(get_global_css(), unsafe_allow_html=True)


# ============================================================
# PATH RESOLUTION (cached)
# ============================================================

@lru_cache(maxsize=1)
def find_task_tracker_root() -> Path | None:
    for root in config.POTENTIAL_ROOTS:
        for lib in config.DOCUMENT_LIBRARIES:
            p = root / lib / config.RELATIVE_APP_PATH
            if p.exists():
                return p
    return None

def get_task_tracker_root() -> Path:
    """Get root with error handling for Streamlit context."""
    root = find_task_tracker_root()
    if root is None:
        st.error("Task-Tracker folder not found. Make sure CNA SharePoint is synced locally.")
        st.stop()
    return root


ROOT_DATA_DIR = get_task_tracker_root()
TASKS_XLSX = ROOT_DATA_DIR / config.TASKS_XLSX_NAME
COMPLETED_TASKS_DIR = config.COMPLETED_TASKS_DIR
LIVE_ACTIVITY_DIR   = config.LIVE_ACTIVITY_DIR
PERSONNEL_DIR       = config.PERSONNEL_DIR
LOGO_PATH           = config.LOGO_PATH

def select_cadence(cadence: str):
    st.session_state.selected_cadence = cadence

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
DEFAULT_STATE = {
    "state": "idle",
    "start_utc": None,
    "end_utc": None,
    "pause_start_utc": None,
    "paused_seconds": 0,
    "elapsed_seconds": 0,
    "notes": "",
    "selected_cadence": None,
    "last_task_name": "",
    "reset_counter": 0,
    "confirm_open": False,
    "confirm_rendered": False,
    "partially_complete": False,
    "covering_for": "",
    "live_activity_saved": False,
    "live_task_name": "",
    "live_cadence": "",
    "live_account": "",
    "state_restored": False,
    "restored_task_name": None,
    "restored_account": None,
    "restored_covering_for": None,
}


def initialize_session_state():
    """Initialize session state only once."""
    if "session_initialized" not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.uploaded = False
        for k, v in DEFAULT_STATE.items():
            st.session_state[k] = v


initialize_session_state()


# ============================================================
# RESTORE STATE FROM LIVE ACTIVITY (on page refresh)
# ============================================================
# Get user info (cached)
_user_for_restore = get_os_user().capitalize()
_user_key_for_restore = sanitize_key(_user_for_restore)

if not st.session_state.state_restored:
    st.session_state.state_restored = True
    restored = load_own_live_activity(LIVE_ACTIVITY_DIR, _user_key_for_restore)
    if restored:
        st.session_state.state = restored["state"]
        st.session_state.start_utc = restored["start_utc"]
        st.session_state.paused_seconds = restored["paused_seconds"]
        st.session_state.pause_start_utc = restored["pause_start_utc"]
        st.session_state.selected_cadence = restored["cadence"]
        st.session_state.notes = restored["notes"]
        st.session_state.covering_for = restored["covering_for"]
        st.session_state.live_activity_saved = True
        st.session_state.last_task_name = restored["task_name"]
        st.session_state.restored_task_name = restored["task_name"]
        st.session_state.restored_account = restored["account"]
        st.session_state.restored_covering_for = restored["covering_for"]


# ============================================================
# BUSINESS LOGIC
# ============================================================
def compute_elapsed_seconds() -> int:
    if not st.session_state.start_utc:
        return 0

    now = st.session_state.end_utc if st.session_state.state == "ended" else now_utc()
    base = int((now - st.session_state.start_utc).total_seconds())
    paused = int(st.session_state.paused_seconds)

    if st.session_state.state == "paused" and st.session_state.pause_start_utc:
        paused += int((now - st.session_state.pause_start_utc).total_seconds())

    return max(0, base - paused)


def reset_all():
    """Reset all state and delete live activity file."""
    if "current_user_key" in st.session_state:
        delete_live_activity(LIVE_ACTIVITY_DIR, st.session_state.current_user_key)
    
    old_counter = st.session_state.reset_counter
    st.session_state.reset_counter += 1
    
    # Delete old widget keys
    for key in [f"task_{old_counter}", f"acct_{old_counter}", f"covering_{old_counter}"]:
        st.session_state.pop(key, None)
    
    for k, v in DEFAULT_STATE.items():
        if k != "state_restored":
            st.session_state[k] = v


def start_task():
    st.session_state.state = "running"
    st.session_state.start_utc = now_utc()
    st.session_state.live_activity_saved = False


def pause_task():
    st.session_state.state = "paused"
    st.session_state.pause_start_utc = now_utc()
    if "current_user_key" in st.session_state:
        update_live_activity_state(
            LIVE_ACTIVITY_DIR,
            st.session_state.current_user_key,
            state="paused",
            paused_seconds=st.session_state.paused_seconds,
            pause_start_utc=st.session_state.pause_start_utc,
        )


def resume_task():
    st.session_state.paused_seconds += int(
        (now_utc() - st.session_state.pause_start_utc).total_seconds()
    )
    st.session_state.pause_start_utc = None
    st.session_state.state = "running"
    if "current_user_key" in st.session_state:
        update_live_activity_state(
            LIVE_ACTIVITY_DIR,
            st.session_state.current_user_key,
            state="running",
            paused_seconds=st.session_state.paused_seconds,
            pause_start_utc=None,
        )


def end_task():
    st.session_state.state = "ended"
    st.session_state.end_utc = now_utc()
    if "current_user_key" in st.session_state:
        delete_live_activity(LIVE_ACTIVITY_DIR, st.session_state.current_user_key)


def build_task_record(user_login, full_name, task_name, cadence, account, covering_for, notes, duration_seconds, partially_complete):
    is_covering_for = bool(covering_for and covering_for.strip())
    return {
        "TaskID": str(uuid.uuid4()),
        "UserLogin": user_login,
        "FullName": full_name or None,
        "TaskName": task_name,
        "TaskCadence": cadence,
        "CompanyGroup": account or None,
        "IsCoveringFor": is_covering_for,
        "CoveringFor": covering_for or None,
        "Notes": notes.strip() if notes and notes.strip() else None,
        "PartiallyComplete": partially_complete,
        "StartTimestampUTC": st.session_state.start_utc,
        "EndTimestampUTC": st.session_state.end_utc,
        "DurationSeconds": int(duration_seconds),
        "UploadTimestampUTC": now_utc(),
        "AppVersion": APP_VERSION,
    }


# ============================================================
# CONFIRMATION MODAL
# ============================================================
@st.dialog("Submit?")
def confirm_submit(user_login, full_name, user_key, task_name, selected_account):
    """Confirmation dialog with parameters to avoid global lookups."""
    st.caption(f"**User:** {full_name}")
    st.caption(f"**Task:** {task_name}")
    st.caption(f"**Cadence:** {st.session_state.selected_cadence}")
    
    is_covering = bool(st.session_state.covering_for and st.session_state.covering_for.strip())
    if is_covering:
        st.caption(f"**Covering For:** Yes - {st.session_state.covering_for}")
    else:
        st.caption(f"**Covering For:** No")
    
    st.caption(f"**Account:** {selected_account if selected_account else 'None'}")
    st.caption(f"**Notes:** {st.session_state.notes if st.session_state.notes else 'None'}")
    st.caption(f"**Partially Complete:** {'Yes' if st.session_state.get('submit_partially_complete', False) else 'No'}")

    st.divider()
    
    current_duration = format_hhmmss(st.session_state.elapsed_seconds)
    edited_duration = st.text_input(
        "Duration", 
        value=current_duration,
        key="edit_duration",
        max_chars=8,
    )

    parsed_duration = parse_hhmmss(edited_duration)
    if parsed_duration < 0:
        parsed_duration = st.session_state.elapsed_seconds
        st.warning("Invalid format - using original duration")
    
    st.divider()

    l, r = st.columns(2)

    with l:
        if st.button("Submit", type="primary", width="stretch"):
            record = build_task_record(
                user_login,
                full_name,
                task_name,
                st.session_state.selected_cadence,
                selected_account,
                st.session_state.covering_for,
                st.session_state.notes,
                parsed_duration,
                st.session_state.get('submit_partially_complete', False),
            )
            df = pd.DataFrame([record])
            out_dir = build_out_dir(COMPLETED_TASKS_DIR, user_key, st.session_state.start_utc)
            eastern_start = to_eastern(st.session_state.start_utc)
            fname = f"task_{eastern_start:%Y%m%d_%H%M%S}_{record['TaskID'][:8]}.parquet"
            atomic_write_parquet(df, out_dir / fname)

            st.session_state.confirm_open = False
            st.session_state.confirm_rendered = False
            reset_all()
            st.session_state.uploaded = True
            st.rerun()

    with r:
        if st.button("Cancel", width="stretch"):
            st.session_state.confirm_open = False
            st.session_state.confirm_rendered = False
            st.rerun()

# ============================================================
# LIVE ACTIVITY SECTION DEFINITION
# ============================================================
@st.fragment(run_every=30)
def live_activity_section():
    # Use cached function - exclude current user
    live_activities_df = load_live_activities(LIVE_ACTIVITY_DIR, _exclude_user_key=user_key)

    if not live_activities_df.empty:
        st.divider()
        st.markdown(
            """
            <h3 style="margin-bottom: 0;">
                <span class="live-activity-pulse"></span>
                Live Activity
            </h3>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Tasks currently in progress by other team members")
        
        live_display_df = live_activities_df[
            ["StartTimestampUTC", "FullName", "UserLogin", "TaskName", "Notes"]
        ].copy()

        start_utc = pd.to_datetime(live_display_df["StartTimestampUTC"], utc=True)

        live_display_df["Start Time"] = (
            start_utc.dt.tz_convert(EASTERN_TZ)
            .dt.strftime("%#I:%M %p")
            .str.lower()
        ) + " - " + start_utc.apply(lambda x: format_time_ago(x))
        
        if "Notes" not in live_display_df.columns:
            live_display_df["Notes"] = ""
        live_display_df["Notes"] = live_display_df["Notes"].fillna("")
        
        # --- Resolve display user safely ---
        if "FullName" in live_display_df.columns:
            live_display_df["User"] = (
                live_display_df["FullName"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
        else:
            live_display_df["User"] = ""

        mask_blank = live_display_df["User"].eq("")
        live_display_df.loc[mask_blank, "User"] = (
            live_display_df.loc[mask_blank, "UserLogin"]
            .fillna("")
            .astype(str)
        )

        # --- Final display frame (explicit, no rename magic) ---
        display_cols = pd.DataFrame({
            "User": live_display_df["User"],
            "Task": live_display_df["TaskName"],
            "Start Time": live_display_df["Start Time"],
            "Notes": live_display_df["Notes"],
        })

        st.dataframe(display_cols, hide_index=True, width="stretch")

# ============================================================
# HEADER
# ============================================================
logo_b64 = get_logo_base64(str(LOGO_PATH))

st.markdown(
    f"""
    <div class="header-row">
        <img class="header-logo" src="data:image/png;base64,{logo_b64}" />
        <h1 class="header-title">Logistics Support Task Tracker</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

if st.session_state.uploaded:
    st.toast("Upload Successful", icon="✅")
    st.session_state.uploaded = False


# ============================================================
# MAIN LAYOUT
# ============================================================
spacer_l, left_col, ll, right_col, spacer_r = st.columns([0.4, 4.2, 0.2, 2.0, 0.4])
with left_col:
    st.subheader("Task Definition", anchor=False, text_alignment="center")
with right_col:
    st.subheader("Task Control", anchor=False, text_alignment="center")

spacer_l, left_col, l_space, mid_col, r_space, right_col, spacer_r = st.columns([0.4, 2, 0.2, 2, 0.2, 2, 0.4])

# LEFT COLUMN
with left_col:
    user_login = get_os_user()
    full_name = get_full_name_for_user(str(TASKS_XLSX), user_login)

    user_key = sanitize_key(user_login)
    st.session_state.current_user_key = user_key

    inputs_locked = st.session_state.state != "idle"
    st.text_input("User", value=full_name, disabled=True)

    all_users = load_all_user_full_names(str(TASKS_XLSX))

    # Exclude the current user (by full name)
    covering_options = [""] + [
        u for u in all_users if u != full_name
    ]

    covering_key = f"covering_{st.session_state.reset_counter}"

    # Restore selection if applicable
    if (
        st.session_state.restored_covering_for
        and covering_key not in st.session_state
        and st.session_state.restored_covering_for in covering_options
    ):
        st.session_state[covering_key] = st.session_state.restored_covering_for

    account_options = [""] + load_accounts(str(PERSONNEL_DIR))
    
    acct_key = f"acct_{st.session_state.reset_counter}"
    if st.session_state.restored_account and acct_key not in st.session_state:
        if st.session_state.restored_account in account_options:
            st.session_state[acct_key] = st.session_state.restored_account
    
    selected_account = st.selectbox(
        "Account (optional)",
        account_options,
        key=acct_key,
    )

    covering_toggle = st.toggle("Covering For Someone?", value=False, key="covering_toggle")
    if covering_toggle:
        covering_for = st.selectbox(
            "",
            covering_options,
            disabled=inputs_locked,
            key=covering_key,
            label_visibility="collapsed"
        )
    else:
        covering_for = ""
    st.session_state.covering_for = covering_for

# MIDDLE COLUMN
with mid_col:
    tasks_df = load_tasks(str(TASKS_XLSX))
    task_options = [""] + sorted(tasks_df["TaskName"].unique())
    
    task_key = f"task_{st.session_state.reset_counter}"
    if st.session_state.restored_task_name and task_key not in st.session_state:
        if st.session_state.restored_task_name in task_options:
            st.session_state[task_key] = st.session_state.restored_task_name
    
    task_name = st.selectbox(
        "Task",
        task_options,
        disabled=inputs_locked,
        key=task_key,
    )

    CADENCE_ORDER = ["Daily", "Weekly", "Periodic"]
    available_cadences = (
        tasks_df.loc[tasks_df["TaskName"] == task_name, "TaskCadence"]
        .dropna()
        .unique()
        .tolist()
    )

    if task_name and st.session_state.state == "idle":
        if task_name != st.session_state.last_task_name:
            st.session_state.selected_cadence = None
            st.session_state.last_task_name = task_name
        if st.session_state.selected_cadence not in available_cadences:
            st.session_state.selected_cadence = next(
                (c for c in CADENCE_ORDER if c in available_cadences),
                None,
            )

    st.caption("Cadence")
    cols = st.columns(3)
    for col, cadence in zip(cols, CADENCE_ORDER):
        is_selected = st.session_state.selected_cadence == cadence
        disabled = (
            not task_name
            or cadence not in available_cadences
            or (inputs_locked and not is_selected)
        )
        with col:
            st.button(
                cadence,
                disabled=disabled,
                type="primary" if is_selected else "secondary",
                key=f"cad_{cadence}_{st.session_state.reset_counter}",
                on_click=select_cadence,
                width="stretch",
                args=(cadence,),
            )
        
    st.text_area("Notes (optional)", key="notes", height=120)

# RIGHT COLUMN
with right_col:
    st.session_state.elapsed_seconds = compute_elapsed_seconds()
    
    hh, mm = format_hh_mm_parts(st.session_state.elapsed_seconds)
    colon_class = "blink-colon" if st.session_state.state == "running" else ""

    st.markdown(
        f"""
        <div style="text-align:center;margin-bottom:20px;">
            <div style="font-size:36px;font-weight:600;">
                {hh}<span class="{colon_class}">:</span>{mm}
            </div>
            <div style="font-size:15px;color:#6b6b6b;">Elapsed Time</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.state == "idle":
        c1, c2 = st.columns(2)
        can_start = bool(task_name and st.session_state.selected_cadence)
        with c1:
            st.button(
                "Start",
                width="stretch",
                disabled=not can_start,
                help=None if can_start else "Select a task to start time",
                on_click=start_task if can_start else None,
            )
        with c2:
            st.button("End", width="stretch", disabled=True)

    elif st.session_state.state == "running":
        c1, c2 = st.columns(2)
        with c1:
            st.button("Pause", width="stretch", on_click=pause_task)
        with c2:
            st.button("End", width="stretch", on_click=end_task)

    elif st.session_state.state == "paused":
        c1, c2 = st.columns(2)
        with c1:
            st.button("Resume", width="stretch", on_click=resume_task)
        with c2:
            st.button("End", width="stretch", on_click=end_task)

    if st.session_state.state == "ended":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Upload", type="primary", width="stretch"):
                st.session_state.submit_partially_complete = st.session_state.get("partially_complete", False)
                st.session_state.confirm_open = True
                st.session_state.confirm_rendered = False
                st.rerun()
        with c2:
            st.button("Reset", width="stretch", on_click=reset_all)

    if st.session_state.state != "idle":
        pc_left, pc_right = st.columns([1.4, 3])
        with pc_left:
            st.markdown("<div style='padding-top: 8px;'>Partially complete?</div>", unsafe_allow_html=True)
        with pc_right:
            st.toggle(
                "Partially complete",
                key="partially_complete",
                label_visibility="collapsed",
            )

# ============================================================
# SAVE LIVE ACTIVITY (after form values are available)
# ============================================================
if (st.session_state.state in ("running", "paused") and 
    not st.session_state.live_activity_saved and
    task_name and st.session_state.selected_cadence):
    
    save_live_activity(
        LIVE_ACTIVITY_DIR,
        user_key=user_key,
        user_login=user_login,
        full_name=full_name,
        task_name=task_name,
        cadence=st.session_state.selected_cadence,
        account=selected_account,
        covering_for=st.session_state.covering_for,
        notes=st.session_state.notes,
        start_utc=st.session_state.start_utc,
        state=st.session_state.state,
        paused_seconds=st.session_state.paused_seconds,
        pause_start_utc=st.session_state.pause_start_utc,
    )

    st.session_state.live_activity_saved = True
    st.session_state.live_task_name = task_name
    st.session_state.live_cadence = st.session_state.selected_cadence
    st.session_state.live_account = selected_account

# ============================================================
# OPEN CONFIRMATION MODAL (ONE-SHOT)
# ============================================================
if st.session_state.confirm_open and not st.session_state.confirm_rendered:
    st.session_state.confirm_rendered = True
    confirm_submit(user_login, full_name, user_key, task_name, selected_account)


live_activity_section()

# ============================================================
# TODAY'S TASKS
# ============================================================
st.divider()

col_title, col_toggle = st.columns([6, 2], vertical_alignment="center")

with col_title:
    st.subheader("Today's Activity", anchor=False)

with col_toggle:
    with st.container(horizontal_alignment="right"):
        show_all_users = st.toggle("Show all users?", value=True, key="show_all_users")

# Use cached function
if show_all_users:
    recent_df = load_recent_tasks(COMPLETED_TASKS_DIR, user_key=None, limit=50)
else:
    recent_df = load_recent_tasks(COMPLETED_TASKS_DIR, user_key=user_key, limit=50)

if not recent_df.empty:
    recent_df["Duration"] = recent_df["DurationSeconds"].apply(format_hhmmss)
    recent_df["Uploaded"] = pd.to_datetime(
        recent_df["EndTimestampUTC"], utc=True
    ).apply(lambda x: format_time_ago(x))

    if "PartiallyComplete" not in recent_df.columns:
        recent_df["PartiallyComplete"] = pd.Series([pd.NA] * len(recent_df), dtype="boolean")
    else:
        recent_df["PartiallyComplete"] = recent_df["PartiallyComplete"].astype("boolean")

    recent_df["Partially Completed?"] = recent_df["PartiallyComplete"].fillna(False).astype(bool)

    if "Notes" not in recent_df.columns:
        recent_df["Notes"] = ""
    recent_df["Notes"] = recent_df["Notes"].fillna("")

    if "FullName" not in recent_df.columns:
        recent_df["FullName"] = ""

    recent_df["DisplayUser"] = recent_df["FullName"].fillna("").astype(str).str.strip()
    mask_blank = recent_df["DisplayUser"].eq("")
    recent_df.loc[mask_blank, "DisplayUser"] = recent_df.loc[mask_blank, "UserLogin"].fillna("").astype(str)

    display_df = recent_df.rename(
        columns={"TaskName": "Task", "DisplayUser": "User"}
    )[["User", "Task", "Partially Completed?", "Uploaded", "Duration", "Notes"]]

    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Partially Completed?": st.column_config.CheckboxColumn(
                "Partially Completed?", disabled=True, width=1
            ),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
            "Uploaded": st.column_config.TextColumn("Uploaded", width=1),
        },
    )
else:
    st.info("No tasks completed today.")

# ============================================================
# FOOTER
# ============================================================
st.caption(f"\n\n\nApp version: {APP_VERSION}", text_alignment="center")

if st.session_state.state == "running":
    st_autorefresh(interval=10_000, key="timer")
