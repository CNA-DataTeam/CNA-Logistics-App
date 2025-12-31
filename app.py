import streamlit as st
import pandas as pd
import uuid
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from streamlit_autorefresh import st_autorefresh

# =============================
# CONFIG
# =============================
APP_VERSION = "1.3.3"

st.set_page_config(
    page_title="Logistics Support Task Tracker",
    layout="centered"
)

def get_onedrive_business_root() -> Path:
    """
    Returns the current user's OneDrive for Business root.
    """
    root = (
        os.environ.get("OneDriveCommercial")
        or os.environ.get("ONEDRIVECOMMERCIAL")
        or os.environ.get("OneDrive")
    )

    if not root:
        st.error(
            "OneDrive folder not found. "
            "Please ensure OneDrive is installed and signed in."
        )
        st.stop()

    return Path(root)

# ---------- GLOBAL STYLING ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600&family=Work+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Work Sans', sans-serif;
    }

    h1, h2, h3 {
        font-family: 'Poppins', sans-serif;
        font-weight: 600;
    }

    .circle-btn button {
        border-radius: 50%;
        width: 120px;
        height: 120px;
        font-size: 18px;
        font-weight: 600;
    }

    .green button {
        color: #2e7d32;
        font-weight: 600;
    }

    .red button {
        color: #00B19E;
        font-weight: 600;
    }

    /* Tighten cadence buttons row */
    .cadence-row button {
        width: 100%;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================
# PATHS (robust resolution)
# =============================
ONEDRIVE_ROOT = get_onedrive_business_root()

TASKS_CSV = (
    ONEDRIVE_ROOT
    / st.secrets["TASKS_CSV_RELATIVE"]
).resolve()

ACCOUNTS_XLSX = (
    ONEDRIVE_ROOT
    / st.secrets["ACCOUNTS_XLSX_RELATIVE"]
).resolve()

if not TASKS_CSV.exists():
    st.error(f"Tasks file not found:\n{TASKS_CSV}")
    st.stop()

if not ACCOUNTS_XLSX.exists():
    st.error(f"Accounts file not found:\n{ACCOUNTS_XLSX}")
    st.stop()

ROOT_DATA_DIR = (
    ONEDRIVE_ROOT
    / st.secrets["ROOT_DATA_DIR_RELATIVE"]
).resolve()

if not ROOT_DATA_DIR.exists():
    st.error(f"Root data directory not found:\n{ROOT_DATA_DIR}")
    st.stop()

LOGO_PATH = Path(
    r"\\Corp-filesrv-01\dfs_920$\Reporting\Power BI Branding\CNA-Logo_Greenx4.png"
)

# =============================
# HELPERS
# =============================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def get_os_user() -> str:
    return os.getenv("USERNAME") or os.getenv("USER") or "unknown"

def sanitize_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_\-\.]", "", value)
    return value

def format_hhmmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

@st.cache_data(ttl=3600)
def load_tasks(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["IsActive"].astype(int) == 1].copy()
    df["TaskName"] = df["TaskName"].astype(str).str.strip()
    df["TaskCadence"] = df["TaskCadence"].astype(str).str.strip().str.title()
    return df

@st.cache_data(ttl=3600)
def load_accounts_from_excel(path: Path) -> list[str]:
    if not path.exists():
        return []
    df = pd.read_excel(path, sheet_name="CNA Personnel", engine="openpyxl")
    if "Company Group USE" not in df.columns:
        return []
    return sorted(
        df["Company Group USE"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

def build_out_dir(root: Path, user_key: str, ts: datetime) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"Root data directory does not exist: {root}")

    return (
        root
        / f"user={user_key}"
        / f"year={ts.year}"
        / f"month={ts.month:02d}"
        / f"day={ts.day:02d}"
    )

# =============================
# PARQUET
# =============================
PARQUET_SCHEMA = pa.schema(
    [
        ("TaskID", pa.string()),
        ("UserLogin", pa.string()),
        ("UserDisplayName", pa.string()),
        ("TaskName", pa.string()),
        ("TaskCadence", pa.string()),
        ("CompanyGroup", pa.string()),
        ("Notes", pa.string()),
        ("StartTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("EndTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("DurationSeconds", pa.int64()),
        ("UploadTimestampUTC", pa.timestamp("us", tz="UTC")),
        ("AppVersion", pa.string()),
    ]
)

def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)
    pq.write_table(table, tmp)
    tmp.replace(path)

# =============================
# SESSION STATE INIT
# =============================
if "state" not in st.session_state:
    st.session_state.state = "idle"
if "start_utc" not in st.session_state:
    st.session_state.start_utc = None
if "end_utc" not in st.session_state:
    st.session_state.end_utc = None
if "pause_start_utc" not in st.session_state:
    st.session_state.pause_start_utc = None
if "paused_seconds" not in st.session_state:
    st.session_state.paused_seconds = 0
if "elapsed_seconds" not in st.session_state:
    st.session_state.elapsed_seconds = 0

# Notes is widget-backed, so we init before widget creation
if "notes" not in st.session_state:
    st.session_state.notes = ""

# Cadence selection is NOT a widget, but we keep it in session
if "selected_cadence" not in st.session_state:
    st.session_state.selected_cadence = None
if "last_task_name" not in st.session_state:
    st.session_state.last_task_name = ""

# Reset counter to force clean UI reset for selectboxes
if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

if "uploaded" not in st.session_state:
    st.session_state.uploaded = False

def compute_elapsed_seconds() -> int:
    """Deterministic elapsed time. If ended, use end_utc as the clock."""
    if not st.session_state.start_utc:
        return 0

    as_of = st.session_state.end_utc if (st.session_state.state == "ended" and st.session_state.end_utc) else now_utc()
    base = int((as_of - st.session_state.start_utc).total_seconds())
    paused = int(st.session_state.paused_seconds or 0)

    if st.session_state.state == "paused" and st.session_state.pause_start_utc:
        paused += int((as_of - st.session_state.pause_start_utc).total_seconds())

    return max(0, base - paused)

def reset_all() -> None:
    # Force widgets to rebuild fresh
    st.session_state.reset_counter += 1

    # Clear widget-backed keys (safe via pop)
    st.session_state.pop("notes", None)

    # Reset non-widget state
    st.session_state.selected_cadence = None
    st.session_state.last_task_name = ""

    st.session_state.state = "idle"
    st.session_state.start_utc = None
    st.session_state.end_utc = None
    st.session_state.pause_start_utc = None
    st.session_state.paused_seconds = 0
    st.session_state.elapsed_seconds = 0

# =============================
# HEADER
# =============================
left, center, right = st.columns([1, 1, 1])
with center:
    st.image(LOGO_PATH, width=90)

st.markdown(
    "<h1 style='text-align: center; margin-top: 10px;'>Logistics Support Task Tracker</h1>",
    unsafe_allow_html=True,
)

# Toast (one-time)
if st.session_state.get("uploaded"):
    st.toast("Upload Successful", icon="✅")
    st.session_state.uploaded = False

# =============================
# USER / INPUTS
# =============================
user_login = get_os_user()
user_display = user_login.capitalize()
user_key = sanitize_key(user_login)

inputs_locked = st.session_state.state != "idle"

st.text_input("User", value=user_display, disabled=True)

# =============================
# TASK SELECTION
# =============================
tasks_df = load_tasks(TASKS_CSV)

task_names = (
    tasks_df["TaskName"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
    .tolist()
)
task_options = [""] + sorted(task_names)

task_name = st.selectbox(
    "Task name",
    options=task_options,
    index=0,
    disabled=inputs_locked,
    key=f"task_name_{st.session_state.reset_counter}",
)

if not task_name:
    st.info("Select a task to begin.")

# =============================
# CADENCE BUTTONS (Daily / Weekly / Periodic)
# =============================
CADENCE_ORDER = ["Daily", "Weekly", "Periodic"]  # most frequent → least frequent

available_cadences: list[str] = []
if task_name:
    available_cadences = (
        tasks_df.loc[tasks_df["TaskName"] == task_name, "TaskCadence"]
        .dropna()
        .astype(str)
        .str.title()
        .unique()
        .tolist()
    )
    available_cadences = [c for c in available_cadences if c in CADENCE_ORDER]

# Force selection + default to most frequent when idle
if st.session_state.state == "idle":
    if task_name != st.session_state.last_task_name:
        st.session_state.selected_cadence = None
        st.session_state.last_task_name = task_name

    if task_name and st.session_state.selected_cadence not in available_cadences:
        st.session_state.selected_cadence = next(
            (c for c in CADENCE_ORDER if c in available_cadences),
            None
        )

st.caption("Cadence")
c1, c2, c3 = st.columns(3)

for col, cadence in zip([c1, c2, c3], CADENCE_ORDER):
    is_available = cadence in available_cadences
    is_selected = st.session_state.selected_cadence == cadence

    with col:
        if st.button(
            cadence,
            key=f"cad_{cadence}_{st.session_state.reset_counter}",
            disabled=(
                inputs_locked
                or not task_name
                or not is_available
            ),
            type="primary" if is_selected else "secondary",
        ):
            st.session_state.selected_cadence = cadence
            st.rerun()

# =============================
# ACCOUNT SELECTION (AFTER CADENCE)
# =============================
accounts = load_accounts_from_excel(ACCOUNTS_XLSX)
selected_account = st.selectbox(
    "Account (optional)",
    [""] + accounts,
    disabled=inputs_locked,
    key=f"selected_account_{st.session_state.reset_counter}",
)

# =============================
# NOTES (editable until upload)
# =============================
st.text_area(
    "Notes (optional)",
    placeholder="Add any relevant context, blockers, or details here…",
    key="notes",
    height=120
)

# =============================
# TIMER (lightweight + deterministic)
# =============================
if st.session_state.state == "running":
    st_autorefresh(interval=1000, key="task_timer")

st.session_state.elapsed_seconds = compute_elapsed_seconds()
timer_display = format_hhmmss(st.session_state.elapsed_seconds)

# =============================
# CONTROLS
# =============================
st.subheader("Task Control", anchor=False)

main, side = st.columns([1, 1])

with main:
    if st.session_state.state == "idle":
        start_col, reset_col = st.columns(2)

        with start_col:
            st.markdown('<div class="circle-btn">', unsafe_allow_html=True)

            can_start = bool(task_name) and bool(st.session_state.selected_cadence)

            if st.button("Start", disabled=not can_start, key="start_btn"):
                st.session_state.state = "running"
                st.session_state.start_utc = now_utc()
                st.session_state.end_utc = None
                st.session_state.pause_start_utc = None
                st.session_state.paused_seconds = 0
                st.session_state.elapsed_seconds = 0
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        with reset_col:
            st.markdown('<div class="red">', unsafe_allow_html=True)
            if st.button("Reset", key="reset_idle"):
                reset_all()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    else:
        st.metric("Elapsed Time", timer_display)

with side:
    if st.session_state.state == "running":
        if st.button("Pause", key="pause_btn"):
            st.session_state.state = "paused"
            st.session_state.pause_start_utc = now_utc()
            st.rerun()

    elif st.session_state.state == "paused":
        if st.button("Resume", key="resume_btn"):
            if st.session_state.pause_start_utc:
                st.session_state.paused_seconds += int(
                    (now_utc() - st.session_state.pause_start_utc).total_seconds()
                )
            st.session_state.pause_start_utc = None
            st.session_state.state = "running"
            st.rerun()

    if st.session_state.state in ["running", "paused"]:
        if st.button("End", key="end_btn"):
            # finalize paused time if ending during a pause
            if st.session_state.state == "paused" and st.session_state.pause_start_utc:
                st.session_state.paused_seconds += int(
                    (now_utc() - st.session_state.pause_start_utc).total_seconds()
                )
                st.session_state.pause_start_utc = None

            st.session_state.state = "ended"
            st.session_state.end_utc = now_utc()
            st.session_state.elapsed_seconds = compute_elapsed_seconds()
            st.rerun()

# =============================
# UPLOAD / RESET (ENDED)
# =============================
if st.session_state.state == "ended":
    st.divider()
    u, r = st.columns(2)

    with u:
        st.markdown('<div class="green">', unsafe_allow_html=True)
        if st.button("Upload", key="upload_btn"):
            record = {
                "TaskID": str(uuid.uuid4()),
                "UserLogin": user_login,
                "UserDisplayName": user_display,
                "TaskName": task_name,
                "TaskCadence": st.session_state.selected_cadence,
                "CompanyGroup": (selected_account or None),
                "Notes": st.session_state.notes.strip() or None,
                "StartTimestampUTC": st.session_state.start_utc,
                "EndTimestampUTC": st.session_state.end_utc,
                "DurationSeconds": int(st.session_state.elapsed_seconds),
                "UploadTimestampUTC": now_utc(),
                "AppVersion": APP_VERSION,
            }

            df = pd.DataFrame([record])

            out_dir = build_out_dir(ROOT_DATA_DIR, user_key, st.session_state.start_utc)
            fname = (
                f"task_{st.session_state.start_utc:%Y%m%d_%H%M%S}_"
                f"{record['TaskID'][:8]}.parquet"
            )

            atomic_write_parquet(df, out_dir / fname)

            st.session_state.uploaded = True
            reset_all()
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with r:
        st.markdown('<div class="red">', unsafe_allow_html=True)
        if st.button("Reset", key="reset_ended"):
            reset_all()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

st.caption(f"Data path: {ROOT_DATA_DIR}")
st.caption(f"App version: {APP_VERSION}")