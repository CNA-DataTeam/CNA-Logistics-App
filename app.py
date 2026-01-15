# ============================================================
# IMPORTS
# ============================================================
import streamlit as st
import pandas as pd
import uuid
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from streamlit_autorefresh import st_autorefresh


# ============================================================
# APP CONFIG
# ============================================================
APP_VERSION = "1.5.0"

# Eastern timezone for display
EASTERN_TZ = ZoneInfo("America/New_York")

st.set_page_config(
    page_title="Task Tracker",
    layout="wide",
)

# ============================================================
# GLOBAL STYLING
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600&family=Work+Sans:wght@400;500;600&display=swap');

    @keyframes blink { 50% { opacity: 0; } }

    html, body, [class*="css"] {
        font-family: 'Work Sans', sans-serif;
    }

    h1, h2, h3 {
        font-family: 'Poppins', sans-serif;
        font-weight: 600;
    }

    .blink-colon {
        animation: blink 1s steps(1, start) infinite;
    }

    .reset-button div > button {
        background-color: #C30000 !important;
        color: white !important;
        border: none !important;
    }

    .reset-button div > button:hover {
        background-color: #A00000 !important;
    }

    .reset-button div > button:focus {
        box-shadow: none !important;
    }

    iframe[title="streamlit_autorefresh.st_autorefresh"] {
        display:none;
    }

    .stDataFrame thead th {
        font-weight: 800 !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# PATH RESOLUTION
# ============================================================

def get_os_user() -> str:
    """
    Best-effort attempt to retrieve the user's full display name.
    Falls back to username if unavailable.
    """
    for key in ("DISPLAYNAME", "FULLNAME"):
        value = os.getenv(key)
        if value:
            return value.strip()

    user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
    return user.replace(".", " ").replace("_", " ").title()

def find_task_tracker_root() -> Path:
    user = get_os_user()
    roots = [
        Path(f"C:/Users/{user}/clarkinc.biz"),
        Path(f"C:/Users/{user}/OneDrive - clarkinc.biz"),
        Path(f"C:/Users/{user}/OneDrive"),
    ]
    libraries = [
        "Clark National Accounts - Documents",
        "Documents - Clark National Accounts",
    ]
    rel = Path("Logistics and Supply Chain/Logistics Support/Task-Tracker")

    for root in roots:
        for lib in libraries:
            p = root / lib / rel
            if p.exists():
                return p

    st.error("Task-Tracker folder not found. Make sure CNA SharePoint is synced locally.")
    st.stop()


ROOT_DATA_DIR = find_task_tracker_root()
TASKS_CSV = ROOT_DATA_DIR / "TasksAndTargets.csv"
ACCOUNTS_XLSX = (
    ROOT_DATA_DIR.parents[2]
    / "Data and Analytics"
    / "Resources"
    / "CNA Personnel - Temporary.xlsx"
)

LOGO_PATH = Path(
    r"\\Corp-filesrv-01\dfs_920$\Reporting\Power BI Branding\CNA-Logo_Greenx4.png"
)

# ============================================================
# HELPERS
# ============================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_eastern(dt: datetime) -> datetime:
    """Convert a datetime to Eastern timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN_TZ)


def sanitize_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_\-\.]", "", value)
    return value


def format_hhmm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}"


def format_hhmmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}"


def format_hh_mm_parts(seconds: int) -> tuple[str, str]:
    seconds = max(0, int(seconds))
    return f"{seconds//3600:02d}", f"{(seconds%3600)//60:02d}"


def parse_hhmmss(time_str: str) -> int:
    """Parse HH:MM:SS string to seconds."""
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return h * 3600 + m * 60
    except (ValueError, AttributeError):
        pass
    return -1


def select_cadence(cadence: str):
    st.session_state.selected_cadence = cadence


# ============================================================
# PARQUET + IO
# ============================================================
PARQUET_SCHEMA = pa.schema(
    [
        ("TaskID", pa.string()),
        ("UserLogin", pa.string()),
        ("TaskName", pa.string()),
        ("TaskCadence", pa.string()),
        ("CompanyGroup", pa.string()),
        ("CoveringFor", pa.string()),
        ("Notes", pa.string()),
        ("PartiallyComplete", pa.bool_()),
        ("StartTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("EndTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("DurationSeconds", pa.int64()),
        ("UploadTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("AppVersion", pa.string()),
    ]
)


def build_out_dir(root: Path, user_key: str, ts: datetime) -> Path:
    eastern_ts = to_eastern(ts)
    return (
        root / "AllTasks"
        / f"user={user_key}"
        / f"year={eastern_ts.year}"
        / f"month={eastern_ts.month:02d}"
        / f"day={eastern_ts.day:02d}"
    )


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)
    pq.write_table(table, tmp)
    tmp.replace(path)


def load_recent_tasks(root: Path, user_key: str | None = None, limit: int = 50) -> pd.DataFrame:
    """Load recent tasks. If user_key is None, load from all users."""
    base = root / "AllTasks"
    if not base.exists():
        return pd.DataFrame()

    # Get today's date in Eastern timezone
    today_eastern = to_eastern(now_utc()).date()

    # Determine which directories to search
    if user_key:
        search_paths = [base / f"user={user_key}"]
    else:
        search_paths = list(base.glob("user=*"))

    files = []
    for search_path in search_paths:
        if search_path.exists():
            # Only look at today's folder for efficiency
            today_folder = (
                search_path
                / f"year={today_eastern.year}"
                / f"month={today_eastern.month:02d}"
                / f"day={today_eastern.day:02d}"
            )
            if today_folder.exists():
                files.extend(today_folder.glob("*.parquet"))

    if not files:
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    return df.sort_values("StartTimestampUTC", ascending=False).head(limit)


# ============================================================
# DATA LOADERS
# ============================================================
@st.cache_data(ttl=3600)
def load_tasks(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["IsActive"].astype(int) == 1].copy()
    df["TaskName"] = df["TaskName"].str.strip()
    df["TaskCadence"] = df["TaskCadence"].str.strip().str.title()
    return df


@st.cache_data(ttl=3600)
def load_accounts(path: Path) -> list[str]:
    df = pd.read_excel(path, sheet_name="CNA Personnel", engine="openpyxl")
    return df["Company Group USE"].dropna().astype(str).str.strip().unique().tolist()


# ============================================================
# SESSION STATE
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
}

st.session_state.setdefault("uploaded", False)

for k, v in DEFAULT_STATE.items():
    st.session_state.setdefault(k, v)

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
    old_counter = st.session_state.reset_counter
    st.session_state.reset_counter += 1
    
    # Delete old widget keys so new ones start fresh
    keys_to_delete = [f"task_{old_counter}", f"acct_{old_counter}", f"covering_{old_counter}"]
    for key in keys_to_delete:
        st.session_state.pop(key, None)
    
    for k in DEFAULT_STATE:
        st.session_state[k] = DEFAULT_STATE[k]

def start_task():
    st.session_state.state = "running"
    st.session_state.start_utc = now_utc()


def pause_task():
    st.session_state.state = "paused"
    st.session_state.pause_start_utc = now_utc()


def resume_task():
    st.session_state.paused_seconds += int(
        (now_utc() - st.session_state.pause_start_utc).total_seconds()
    )
    st.session_state.pause_start_utc = None
    st.session_state.state = "running"


def end_task():
    st.session_state.state = "ended"
    st.session_state.end_utc = now_utc()


def build_task_record(user, task_name, cadence, account, covering_for, notes, duration_seconds, partially_complete):
    return {
        "TaskID": str(uuid.uuid4()),
        "UserLogin": user,
        "TaskName": task_name,
        "TaskCadence": cadence,
        "CompanyGroup": account or None,
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
def confirm_submit():

    # Show non-editable fields
    st.caption(f"**User:** {user}")
    st.caption(f"**Task:** {task_name}")
    st.caption(f"**Cadence:** {st.session_state.selected_cadence}")
    if st.session_state.covering_for:
        st.caption(f"**Covering for:** {st.session_state.covering_for}")
    st.caption(f"**Account:** {selected_account if selected_account else 'None'}")
    st.caption(f"**Notes:** {st.session_state.notes if st.session_state.notes else 'None'}")
    st.caption(f"**Partially Complete:** {'Yes' if st.session_state.get('submit_partially_complete', False) else 'No'}")

    st.divider()
    
    # Editable duration
    current_duration = format_hhmmss(st.session_state.elapsed_seconds)
    edited_duration = st.text_input(
        "Duration", 
        value=current_duration,
        key="edit_duration",
        max_chars=8,
    )

    # Parse and validate - fall back to original if invalid
    parsed_duration = parse_hhmmss(edited_duration)
    if parsed_duration < 0:
        parsed_duration = st.session_state.elapsed_seconds
        st.warning("Invalid format - using original duration")
    
    st.divider()

    l, r = st.columns(2)

    with l:
        if st.button("Submit", type="primary", width="stretch"):
            record = build_task_record(
                user,
                task_name,
                st.session_state.selected_cadence,
                selected_account,
                st.session_state.covering_for,
                st.session_state.notes,
                parsed_duration,
                st.session_state.get('submit_partially_complete', False),
            )
            df = pd.DataFrame([record])
            out_dir = build_out_dir(ROOT_DATA_DIR, user_key, st.session_state.start_utc)
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
# HEADER
# ============================================================
_, c, _ = st.columns([1, 1, 1])
with c:
    st.image(LOGO_PATH, width=90)

st.markdown(
    "<h1 style='text-align:center;margin-top:10px;'>Logistics Support Task Tracker</h1>",
    unsafe_allow_html=True,
)
st.divider()

if st.session_state.uploaded:
    st.toast("Upload Successful", icon="✅")
    st.session_state.uploaded = False


# ============================================================
# MAIN LAYOUT
# ============================================================
spacer_l, left_col, spacer_m, right_col, spacer_r = st.columns([1, 2, 0.5, 2, 1])

# LEFT
with left_col:
    st.subheader("Task Definition")

    user = get_os_user()
    user = user.capitalize()
    user_key = sanitize_key(user)

    inputs_locked = st.session_state.state != "idle"
    st.text_input("User", value=user, disabled=True)
    
    # Covering for dropdown - locked after task starts
    covering_for = st.selectbox(
        "Covering for (optional)",
        [""],  # Blank for now - populate with user list later if needed
        disabled=inputs_locked,
        key=f"covering_{st.session_state.reset_counter}",
    )
    st.session_state.covering_for = covering_for

    tasks_df = load_tasks(TASKS_CSV)
    task_name = st.selectbox(
        "Task",
        [""] + sorted(tasks_df["TaskName"].unique()),
        disabled=inputs_locked,
        key=f"task_{st.session_state.reset_counter}",
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

    # Account is now always editable (not locked after task starts)
    selected_account = st.selectbox(
        "Account (optional)",
        [""] + load_accounts(ACCOUNTS_XLSX),
        key=f"acct_{st.session_state.reset_counter}",
    )

    st.text_area("Notes (optional)", key="notes", height=120)

# RIGHT
with right_col:
    st.subheader("Task Control")

    st.session_state.elapsed_seconds = compute_elapsed_seconds()
    
    hh, mm = format_hh_mm_parts(st.session_state.elapsed_seconds)
    colon_class = "blink-colon" if st.session_state.state == "running" else ""

    st.markdown(
        f"""
        <div style="text-align:center;margin-bottom:20px;">
            <div style="font-size:36px;font-weight:600;">
                {hh}<span class="{colon_class}">:</span>{mm}
            </div>
            <div style="font-size:12px;color:#6b6b6b;">Elapsed Time</div>
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
                # Capture partially_complete value before rerun
                st.session_state.submit_partially_complete = st.session_state.get("partially_complete", False)
                st.session_state.confirm_open = True
                st.session_state.confirm_rendered = False
                st.rerun()
        with c2:
            st.button("Reset", width="stretch", on_click=reset_all)

    # Partially complete toggle - always visible after buttons
    if st.session_state.state != "idle":
        pc_left, pc_right = st.columns([1.09, 3])
        with pc_left:
            st.markdown("<div style='padding-top: 8px;'>Partially complete?</div>", unsafe_allow_html=True)
        with pc_right:
            st.toggle(
                "Partially complete",
                key="partially_complete",
                label_visibility="collapsed",
            )

# ============================================================
# OPEN CONFIRMATION MODAL (ONE-SHOT)
# ============================================================
if st.session_state.confirm_open and not st.session_state.confirm_rendered:
    st.session_state.confirm_rendered = True
    confirm_submit()

# ============================================================
# TODAY'S TASKS
# ============================================================
st.divider()
st.subheader("Today's Activity")

# Toggle between all users and current user
show_all_users = st.toggle(
    "Show all users",
    value=True,
    key="show_all_users",
)

if show_all_users:
    recent_df = load_recent_tasks(ROOT_DATA_DIR, user_key=None, limit=50)
else:
    recent_df = load_recent_tasks(ROOT_DATA_DIR, user_key=user_key, limit=50)

if not recent_df.empty:
    recent_df["Duration"] = recent_df["DurationSeconds"].apply(format_hhmmss)
    recent_df["Date Time"] = (
        pd.to_datetime(recent_df["EndTimestampUTC"], utc=True)
        .dt.tz_convert(EASTERN_TZ)
        .dt.strftime("%#I:%M %p")
        .str.lower()
    )
    
    # Handle PartiallyComplete column - may not exist in older records
    if "PartiallyComplete" not in recent_df.columns:
        recent_df["PartiallyComplete"] = pd.Series([pd.NA] * len(recent_df), dtype="boolean")
    else:
        # Normalize dtype to pandas nullable boolean to avoid FutureWarning on fillna downcasting
        recent_df["PartiallyComplete"] = recent_df["PartiallyComplete"].astype("boolean")

    # Streamlit CheckboxColumn is happiest with plain bools
    recent_df["Partially Completed?"] = recent_df["PartiallyComplete"].fillna(False).astype(bool)
    
    # Handle Notes column
    if "Notes" not in recent_df.columns:
        recent_df["Notes"] = ""
    recent_df["Notes"] = recent_df["Notes"].fillna("")
    
    # Display table with selected columns
    display_df = recent_df.rename(
        columns={
            "TaskName": "Task",
            "UserLogin": "User",
        }
    )[["User", "Task", "Partially Completed?", "Date Time", "Duration", "Notes"]]
    
    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Partially Completed?": st.column_config.CheckboxColumn(
                "Partially Completed?",
                disabled=True,
                width=1,
            ),
            "Notes": st.column_config.TextColumn(
                "Notes",
                width="large",
            ),
            "Date Time": st.column_config.TextColumn(
                "Uploaded At",
                width=1,
            ),
        },
    )
else:
    st.info("No tasks completed today.")

# ============================================================
# FOOTER
# ============================================================
st.caption(f"\n\nApp version: {APP_VERSION}")

if st.session_state.state == "running":
    st_autorefresh(interval=60_000, key="timer")