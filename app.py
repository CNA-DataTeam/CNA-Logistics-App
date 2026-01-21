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
from functools import lru_cache
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from streamlit_autorefresh import st_autorefresh
import base64


# ============================================================
# APP CONFIG
# ============================================================
APP_VERSION = "1.7.7" 

# Eastern timezone for display
EASTERN_TZ = ZoneInfo("America/New_York")

st.set_page_config(
    page_title="Task Tracker",
    layout="wide",
)

# ============================================================
# GLOBAL STYLING (cached to avoid re-processing)
# ============================================================
@st.cache_data
def get_global_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600&family=Work+Sans:wght@400;500;600&display=swap');

    @keyframes blink { 50% { opacity: 0; } }

    html, body, [class*="css"] {
        font-family: 'Work Sans', sans-serif;
    }

    .header-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 14px;
        margin-top: 10px;
        margin-bottom: 6px;
    }

    .header-logo {
        width: 80px;
        height: auto;
    }

    .header-title {
        margin: 0 !important;
        text-align: center;
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

    .live-activity-pulse {
        display: inline-block;
        width: 12px;
        height: 12px;
        background-color: #C30000;
        border-radius: 100%;
        margin-right: 2px;
        animation: pulse 1.5s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.2); }
    }
    </style>
    """

st.markdown(get_global_css(), unsafe_allow_html=True)


# ============================================================
# PATH RESOLUTION (cached)
# ============================================================
@lru_cache(maxsize=1)
def get_os_user() -> str:
    """
    Best-effort attempt to retrieve the user's full display name.
    Falls back to username if unavailable. Cached for performance.
    """
    for key in ("DISPLAYNAME", "FULLNAME"):
        value = os.getenv(key)
        if value:
            return value.strip()

    user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
    return user.replace(".", " ").replace("_", " ").title()

@lru_cache(maxsize=1)
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

    return None  # Return None instead of stopping here

def get_task_tracker_root() -> Path:
    """Get root with error handling for Streamlit context."""
    root = find_task_tracker_root()
    if root is None:
        st.error("Task-Tracker folder not found. Make sure CNA SharePoint is synced locally.")
        st.stop()
    return root


ROOT_DATA_DIR = get_task_tracker_root()
TASKS_CSV = ROOT_DATA_DIR / "TasksAndTargets.csv"
LIVE_ACTIVITY_DIR = Path(r"\\Corp-filesrv-01\dfs_920$\Logistics\Task-Tracker\LiveActivity")
PERSONNEL_DIR = Path(r"\\Corp-filesrv-01\dfs_920$\Logistics\Task-Tracker\Personnel")
LOGO_PATH = Path(r"\\Corp-filesrv-01\dfs_920$\Reporting\Power BI Branding\CNA-Logo_Greenx4.png")


# ============================================================
# HELPERS (with caching where beneficial)
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


@lru_cache(maxsize=128)
def sanitize_key(value: str) -> str:
    """Cached sanitization for repeated calls with same value."""
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


def format_time_ago(dt: datetime) -> str:
    """Format a datetime as a relative time string."""
    if dt is None:
        return ""
    now = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    
    if seconds < 60:
        return "less than a minute ago"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hr ago"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days > 1 else ''} ago"


def select_cadence(cadence: str):
    st.session_state.selected_cadence = cadence


# ============================================================
# LOGO CACHING
# ============================================================
@st.cache_data
def get_logo_base64(logo_path: str) -> str:
    """Cache the base64 encoded logo to avoid re-reading on every rerun."""
    try:
        data = Path(logo_path).read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return ""


# ============================================================
# PARQUET SCHEMAS
# ============================================================
PARQUET_SCHEMA = pa.schema(
    [
        ("TaskID", pa.string()),
        ("UserLogin", pa.string()),
        ("TaskName", pa.string()),
        ("TaskCadence", pa.string()),
        ("CompanyGroup", pa.string()),
        ("IsCoveringFor", pa.bool_()),
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

LIVE_ACTIVITY_SCHEMA = pa.schema(
    [
        ("UserKey", pa.string()),
        ("UserLogin", pa.string()),
        ("TaskName", pa.string()),
        ("TaskCadence", pa.string()),
        ("CompanyGroup", pa.string()),
        ("IsCoveringFor", pa.bool_()),
        ("CoveringFor", pa.string()),
        ("Notes", pa.string()),
        ("StartTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("State", pa.string()),
        ("PausedSeconds", pa.int64()),
        ("PauseStartTimestampUTC", pa.timestamp("us", tz="UTC")),
    ]
)


# ============================================================
# PARQUET I/O
# ============================================================
def build_out_dir(root: Path, user_key: str, ts: datetime) -> Path:
    eastern_ts = to_eastern(ts)
    return (
        root / "AllTasks"
        / f"user={user_key}"
        / f"year={eastern_ts.year}"
        / f"month={eastern_ts.month:02d}"
        / f"day={eastern_ts.day:02d}"
    )


def atomic_write_parquet(df: pd.DataFrame, path: Path, schema: pa.Schema = PARQUET_SCHEMA) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_table(table, tmp)
    tmp.replace(path)


# ============================================================
# LIVE ACTIVITY FUNCTIONS
# ============================================================
def save_live_activity(user_key: str, user: str, task_name: str, cadence: str,
                       account: str, covering_for: str, notes: str, start_utc: datetime,
                       state: str = "running", paused_seconds: int = 0,
                       pause_start_utc: datetime = None) -> None:
    """Save live activity to parquet file."""
    LIVE_ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
    
    is_covering_for = bool(covering_for and covering_for.strip())
    
    record = {
        "UserKey": user_key,
        "UserLogin": user,
        "TaskName": task_name,
        "TaskCadence": cadence,
        "CompanyGroup": account or None,
        "IsCoveringFor": is_covering_for,
        "CoveringFor": covering_for or None,
        "Notes": notes.strip() if notes and notes.strip() else None,
        "StartTimestampUTC": start_utc,
        "State": state,
        "PausedSeconds": paused_seconds,
        "PauseStartTimestampUTC": pause_start_utc,
    }
    
    df = pd.DataFrame([record])
    path = LIVE_ACTIVITY_DIR / f"user={user_key}.parquet"
    atomic_write_parquet(df, path, schema=LIVE_ACTIVITY_SCHEMA)


def update_live_activity_state(user_key: str, state: str, paused_seconds: int = 0,
                                pause_start_utc: datetime = None) -> None:
    """Update the state fields in an existing live activity file."""
    path = LIVE_ACTIVITY_DIR / f"user={user_key}.parquet"
    if not path.exists():
        return
    
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return
        df["State"] = state
        df["PausedSeconds"] = paused_seconds
        df["PauseStartTimestampUTC"] = pause_start_utc
        atomic_write_parquet(df, path, schema=LIVE_ACTIVITY_SCHEMA)
    except Exception:
        pass


def load_own_live_activity(user_key: str) -> dict | None:
    """Load the current user's live activity file to restore state."""
    path = LIVE_ACTIVITY_DIR / f"user={user_key}.parquet"
    if not path.exists():
        return None
    
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "task_name": row.get("TaskName"),
            "cadence": row.get("TaskCadence"),
            "account": row.get("CompanyGroup") or "",
            "covering_for": row.get("CoveringFor") or "",
            "notes": row.get("Notes") or "",
            "start_utc": pd.to_datetime(row.get("StartTimestampUTC"), utc=True).to_pydatetime(),
            "state": row.get("State", "running"),
            "paused_seconds": int(row.get("PausedSeconds", 0) or 0),
            "pause_start_utc": pd.to_datetime(row.get("PauseStartTimestampUTC"), utc=True).to_pydatetime() 
                              if pd.notna(row.get("PauseStartTimestampUTC")) else None,
        }
    except Exception:
        return None


def delete_live_activity(user_key: str) -> None:
    """Delete live activity file for user."""
    path = LIVE_ACTIVITY_DIR / f"user={user_key}.parquet"
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


@st.cache_data(ttl=15)
def load_live_activities(_exclude_user_key: str | None = None) -> pd.DataFrame:
    """
    Load all live activities using PyArrow dataset for better performance.
    Cached with 15-second TTL to reduce file I/O while staying reasonably fresh.
    Note: _exclude_user_key is prefixed with _ to exclude from cache key hashing.
    """
    if not LIVE_ACTIVITY_DIR.exists():
        return pd.DataFrame()
    
    files = list(LIVE_ACTIVITY_DIR.glob("user=*.parquet"))
    if not files:
        return pd.DataFrame()
    
    # Filter files before reading if excluding a user
    if _exclude_user_key:
        files = [f for f in files if f.stem.replace("user=", "") != _exclude_user_key]
    
    if not files:
        return pd.DataFrame()
    
    try:
        # Use PyArrow dataset for efficient multi-file reading
        dataset = ds.dataset(files, format="parquet")
        table = dataset.to_table()
        return table.to_pandas()
    except Exception:
        # Fallback to individual file reading
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_parquet(f))
            except Exception:
                pass
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


# ============================================================
# COMPLETED TASKS LOADER
# ============================================================
@st.cache_data(ttl=30)
def load_recent_tasks(_root: Path, user_key: str | None = None, limit: int = 50) -> pd.DataFrame:
    """
    Load recent tasks with caching. Uses PyArrow dataset for efficient reading.
    TTL of 30 seconds balances freshness with performance.
    """
    base = _root / "AllTasks"
    if not base.exists():
        return pd.DataFrame()

    today_eastern = to_eastern(now_utc()).date()

    # Determine which directories to search
    if user_key:
        search_paths = [base / f"user={user_key}"]
    else:
        search_paths = list(base.glob("user=*"))

    files = []
    for search_path in search_paths:
        if search_path.exists():
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

    try:
        # Use PyArrow dataset for efficient multi-file reading
        dataset = ds.dataset(files, format="parquet")
        table = dataset.to_table()
        df = table.to_pandas()
    except Exception:
        # Fallback to individual file reading
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
def load_tasks(path: str) -> pd.DataFrame:
    """Load tasks from CSV. Path as string for cache key compatibility."""
    df = pd.read_csv(path)
    df = df[df["IsActive"].astype(int) == 1].copy()
    df["TaskName"] = df["TaskName"].str.strip()
    df["TaskCadence"] = df["TaskCadence"].str.strip().str.title()
    return df


@st.cache_data(ttl=3600)
def load_accounts(path: str) -> list[str]:
    """Load accounts from parquet. Path as string for cache key compatibility."""
    parquet_files = list(Path(path).glob("*.parquet"))
    if not parquet_files:
        return []
    df = pd.read_parquet(parquet_files[0])
    return df["Company Group USE"].dropna().astype(str).str.strip().unique().tolist()


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
    restored = load_own_live_activity(_user_key_for_restore)
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
        delete_live_activity(st.session_state.current_user_key)
    
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
            st.session_state.current_user_key,
            state="running",
            paused_seconds=st.session_state.paused_seconds,
            pause_start_utc=None,
        )


def end_task():
    st.session_state.state = "ended"
    st.session_state.end_utc = now_utc()
    if "current_user_key" in st.session_state:
        delete_live_activity(st.session_state.current_user_key)


def build_task_record(user, task_name, cadence, account, covering_for, notes, duration_seconds, partially_complete):
    is_covering_for = bool(covering_for and covering_for.strip())
    return {
        "TaskID": str(uuid.uuid4()),
        "UserLogin": user,
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
def confirm_submit(user, user_key, task_name, selected_account):
    """Confirmation dialog with parameters to avoid global lookups."""
    st.caption(f"**User:** {user}")
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
spacer_l, left_col, right_col, spacer_r = st.columns([0.5, 4, 2, 0.5])
with left_col:
    st.subheader("Task Definition", anchor=False, text_alignment="center")
with right_col:
    st.subheader("Task Control", anchor=False, text_alignment="center")

spacer_l, left_col, l_space, mid_col, r_space, right_col, spacer_r = st.columns([0.4, 2, 0.2, 2, 0.2, 2, 0.4])

# LEFT COLUMN
with left_col:
    user = get_os_user().capitalize()
    user_key = sanitize_key(user)
    
    st.session_state.current_user_key = user_key

    inputs_locked = st.session_state.state != "idle"
    st.text_input("User", value=user, disabled=True)
    
    covering_options = [""]
    covering_key = f"covering_{st.session_state.reset_counter}"
    if st.session_state.restored_covering_for and covering_key not in st.session_state:
        if st.session_state.restored_covering_for in covering_options:
            st.session_state[covering_key] = st.session_state.restored_covering_for
    
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

# MIDDLE COLUMN
with mid_col:
    tasks_df = load_tasks(str(TASKS_CSV))
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

# ============================================================
# SAVE LIVE ACTIVITY (after form values are available)
# ============================================================
if (st.session_state.state in ("running", "paused") and 
    not st.session_state.live_activity_saved and
    task_name and st.session_state.selected_cadence):
    
    save_live_activity(
        user_key=user_key,
        user=user,
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
# OPEN CONFIRMATION MODAL (ONE-SHOT)
# ============================================================
if st.session_state.confirm_open and not st.session_state.confirm_rendered:
    st.session_state.confirm_rendered = True
    confirm_submit(user, user_key, task_name, selected_account)

# ============================================================
# LIVE ACTIVITY SECTION (fragment with caching)
# ============================================================
@st.fragment(run_every=30)
def live_activity_section():
    # Use cached function - exclude current user
    live_activities_df = load_live_activities(_exclude_user_key=user_key)

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
        
        live_display_df = live_activities_df.copy()
        
        live_display_df["Start Time"] = (
            pd.to_datetime(live_display_df["StartTimestampUTC"], utc=True)
            .dt.tz_convert(EASTERN_TZ)
            .dt.strftime("%#I:%M %p")
            .str.lower()
        ) + " - " + pd.to_datetime(
            live_display_df["StartTimestampUTC"], utc=True
        ).apply(lambda x: format_time_ago(x))
        
        if "Notes" not in live_display_df.columns:
            live_display_df["Notes"] = ""
        live_display_df["Notes"] = live_display_df["Notes"].fillna("")
        
        display_cols = live_display_df.rename(
            columns={
                "UserLogin": "User",
                "TaskName": "Task",
            }
        )[["User", "Task", "Start Time", "Notes"]]
        
        st.dataframe(
            display_cols,
            hide_index=True,
            width="stretch",
            column_config={
                "Notes": st.column_config.TextColumn("Notes", width="medium"),
                "Start Time": st.column_config.TextColumn("Start Time", width="small"),
            },
        )

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
    recent_df = load_recent_tasks(ROOT_DATA_DIR, user_key=None, limit=50)
else:
    recent_df = load_recent_tasks(ROOT_DATA_DIR, user_key=user_key, limit=50)

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

    display_df = recent_df.rename(
        columns={"TaskName": "Task", "UserLogin": "User"}
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