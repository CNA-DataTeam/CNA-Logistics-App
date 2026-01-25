from __future__ import annotations

import base64
import getpass
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import streamlit as st

EASTERN_TZ = ZoneInfo("America/New_York")

PARQUET_SCHEMA = pa.schema(
    [
        ("TaskID", pa.string()),
        ("UserLogin", pa.string()),
        ("FullName", pa.string()),
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
        ("FullName", pa.string()),
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


@lru_cache(maxsize=1)
def get_os_user() -> str:
    return getpass.getuser()


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
        if len(parts) == 2:
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
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hr ago"
    days = seconds // 86400
    return f"{days} day{'s' if days > 1 else ''} ago"


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


@st.cache_data
def get_logo_base64(logo_path: str) -> str:
    """Cache the base64 encoded logo to avoid re-reading on every rerun."""
    try:
        data = Path(logo_path).read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return ""


def build_out_dir(completed_tasks_dir: Path, user_key: str, ts: datetime) -> Path:
    eastern_ts = to_eastern(ts)
    return (
        completed_tasks_dir
        / f"user={user_key}"
        / f"year={eastern_ts.year}"
        / f"month={eastern_ts.month:02d}"
        / f"day={eastern_ts.day:02d}"
    )


def atomic_write_parquet(
    df: pd.DataFrame,
    path: Path,
    schema: pa.Schema = PARQUET_SCHEMA,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_table(table, tmp)
    tmp.replace(path)


def save_live_activity(
    live_activity_dir: Path,
    user_key: str,
    user_login: str,
    full_name: str,
    task_name: str,
    cadence: str,
    account: str,
    covering_for: str,
    notes: str,
    start_utc: datetime,
    state: str = "running",
    paused_seconds: int = 0,
    pause_start_utc: datetime | None = None,
) -> None:
    """Save live activity to parquet file."""
    live_activity_dir.mkdir(parents=True, exist_ok=True)

    is_covering_for = bool(covering_for and covering_for.strip())

    record = {
        "UserKey": user_key,
        "UserLogin": user_login,
        "FullName": full_name or None,
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
    path = live_activity_dir / f"user={user_key}.parquet"
    atomic_write_parquet(df, path, schema=LIVE_ACTIVITY_SCHEMA)


def update_live_activity_state(
    live_activity_dir: Path,
    user_key: str,
    state: str,
    paused_seconds: int = 0,
    pause_start_utc: datetime | None = None,
) -> None:
    """Update the state fields in an existing live activity file."""
    path = live_activity_dir / f"user={user_key}.parquet"
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


def load_own_live_activity(live_activity_dir: Path, user_key: str) -> dict | None:
    """Load the current user's live activity file to restore state."""
    path = live_activity_dir / f"user={user_key}.parquet"
    if not path.exists():
        return None

    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "full_name": row.get("FullName") or "",
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


def delete_live_activity(live_activity_dir: Path, user_key: str) -> None:
    """Delete live activity file for user."""
    path = live_activity_dir / f"user={user_key}.parquet"
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


@st.cache_data(ttl=15)
def load_live_activities(
    live_activity_dir: Path,
    _exclude_user_key: str | None = None,
) -> pd.DataFrame:
    files = list(live_activity_dir.glob("user=*.parquet"))
    if not files:
        return pd.DataFrame()

    try:
        needed_cols = [
            "FullName",
            "UserLogin",
            "TaskName",
            "StartTimestampUTC",
            "Notes",
        ]

        dataset = ds.dataset(files, format="parquet")
        table = dataset.to_table(columns=needed_cols)
        df = table.to_pandas()

        if _exclude_user_key:
            df = df[df["UserLogin"] != _exclude_user_key]

        return df

    except Exception as exc:
        st.error(f"Failed to load live activities: {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=30)
def load_recent_tasks(_root: Path, user_key: str | None = None, limit: int = 50) -> pd.DataFrame:
    today_eastern = to_eastern(now_utc()).date()

    day_part = (
        f"year={today_eastern.year}/"
        f"month={today_eastern.month:02d}/"
        f"day={today_eastern.day:02d}"
    )

    if user_key:
        files = list((_root / f"user={user_key}" / day_part).glob("*.parquet"))
    else:
        files = list(_root.glob(f"user=*/{day_part}/*.parquet"))

    if not files:
        return pd.DataFrame()

    try:
        needed_cols = [
            "StartTimestampUTC",
            "EndTimestampUTC",
            "DurationSeconds",
            "PartiallyComplete",
            "Notes",
            "FullName",
            "UserLogin",
            "TaskName",
        ]

        dataset = ds.dataset(files, format="parquet")
        table = dataset.to_table(columns=needed_cols)
        df = table.to_pandas()

    except Exception as exc:
        st.error(f"Failed to load recent tasks: {exc}")
        return pd.DataFrame()

    return df.sort_values("StartTimestampUTC", ascending=False).head(limit)


@st.cache_data(ttl=3600)
def load_user_fullname_map(path: str) -> dict[str, str]:
    """
    Load Users sheet mapping:
      - 'User' -> 'Full Name'
    Returns dict keyed by normalized user login.
    """
    try:
        df = pd.read_excel(path, sheet_name="Users")
    except Exception:
        return {}

    if df.empty:
        return {}

    cols = {c.strip().lower(): c for c in df.columns}
    user_col = cols.get("user")
    full_col = cols.get("full name") or cols.get("fullname")

    if not user_col or not full_col:
        return {}

    out: dict[str, str] = {}
    for u, fn in zip(df[user_col], df[full_col]):
        if pd.isna(u):
            continue
        u_norm = str(u).strip().lower()
        if not u_norm:
            continue
        fn_str = "" if pd.isna(fn) else str(fn).strip()
        if fn_str:
            out[u_norm] = fn_str

    return out


def get_full_name_for_user(tasks_xlsx: str, user_login: str) -> str:
    """
    Map OS user login to Full Name using the Users table.
    If no match, return the original user_login.
    """
    mapping = load_user_fullname_map(tasks_xlsx)
    return mapping.get(str(user_login).strip().lower(), user_login)


@st.cache_data(ttl=3600)
def load_all_user_full_names(path: str) -> list[str]:
    """
    Load all Full Names from the Users sheet.
    Returns a sorted list of unique full names.
    """
    try:
        df = pd.read_excel(path, sheet_name="Users")
    except Exception:
        return []

    if df.empty or "Full Name" not in df.columns:
        return []

    names = (
        df["Full Name"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    return sorted(n for n in names.unique() if n)


@st.cache_data(ttl=3600)
def load_tasks(path: str) -> pd.DataFrame:
    """
    Load tasks from the Excel 'Tasks' sheet.
    """
    try:
        df = pd.read_excel(path, sheet_name="Tasks")
    except Exception as exc:
        st.error(f"Failed to read Tasks sheet: {exc}")
        return pd.DataFrame()

    if df.empty:
        return df

    df = df[df["IsActive"].astype(int) == 1].copy()
    df["TaskName"] = df["TaskName"].astype(str).str.strip()
    df["TaskCadence"] = df["TaskCadence"].astype(str).str.strip().str.title()

    return df


@st.cache_data(ttl=3600)
def load_accounts(path: str) -> list[str]:
    parquet_files = list(Path(path).glob("*.parquet"))
    if not parquet_files:
        return []

    df = pd.read_parquet(parquet_files[0], columns=["Company Group USE"])
    return (
        df["Company Group USE"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
