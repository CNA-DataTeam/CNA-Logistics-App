# ============================================================
# IMPORTS
# ============================================================
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


# ============================================================
# APP CONFIG
# ============================================================
APP_VERSION = "1.3.3"

st.set_page_config(
    page_title="Logistics Support Task Tracker",
    layout="centered"
)


# ============================================================
# GLOBAL STYLING
# ============================================================
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
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# PATH RESOLUTION (CNA SHAREPOINT)
# ============================================================
def get_os_user() -> str:
    return os.getenv("USERNAME") or os.getenv("USER") or "unknown"


def get_cna_root() -> Path:
    """
    CNA SharePoint sync root:
    C:\\Users\\<username>\\clarkinc.biz
    """
    root = Path("C:/Users") / get_os_user() / "clarkinc.biz"

    if not root.exists():
        st.error(
            "CNA SharePoint folder not found.\n\n"
            f"Expected:\n{root}\n\n"
            "Please ensure SharePoint is synced locally."
        )
        st.stop()

    return root


CNA_ROOT = get_cna_root()

ROOT_DATA_DIR = (
    CNA_ROOT
    / "Clark National Accounts - Documents"
    / "Logistics and Supply Chain"
    / "Logistics Support"
    / "Task Tracker"
)

TASKS_CSV = ROOT_DATA_DIR / "tasks.csv"

ACCOUNTS_XLSX = (
    CNA_ROOT
    / "Clark National Accounts - Documents"
    / "Data and Analytics"
    / "Resources"
    / "CNA Personnel - Temporary.xlsx"
)

for p in [ROOT_DATA_DIR, TASKS_CSV, ACCOUNTS_XLSX]:
    if not p.exists():
        st.error(f"Required path not found:\n{p}")
        st.stop()

LOGO_PATH = Path(
    r"\\Corp-filesrv-01\dfs_920$\Reporting\Power BI Branding\CNA-Logo_Greenx4.png"
)


# ============================================================
# PURE HELPERS
# ============================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


# ============================================================
# DATA LOADERS
# ============================================================
@st.cache_data(ttl=3600)
def load_tasks(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["IsActive"].astype(int) == 1].copy()
    df["TaskName"] = df["TaskName"].astype(str).str.strip()
    df["TaskCadence"] = df["TaskCadence"].astype(str).str.strip().str.title()
    return df


@st.cache_data(ttl=3600)
def load_accounts(path: Path) -> list[str]:
    df = pd.read_excel(path, sheet_name="CNA Personnel", engine="openpyxl")
    return (
        df["Company Group USE"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )


# ============================================================
# PARQUET WRITER
# ============================================================
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


def build_out_dir(root: Path, user_key: str, ts: datetime) -> Path:
    return (
        root / "/AllTasks"
        / f"user={user_key}"
        / f"year={ts.year}"
        / f"month={ts.month:02d}"
        / f"day={ts.day:02d}"
    )


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)
    pq.write_table(table, tmp)
    tmp.replace(path)


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
    "uploaded": False,
}

for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# BUSINESS LOGIC
# ============================================================
def compute_elapsed_seconds() -> int:
    if not st.session_state.start_utc:
        return 0

    now = (
        st.session_state.end_utc
        if st.session_state.state == "ended"
        else now_utc()
    )

    base = int((now - st.session_state.start_utc).total_seconds())
    paused = int(st.session_state.paused_seconds)

    if st.session_state.state == "paused" and st.session_state.pause_start_utc:
        paused += int((now - st.session_state.pause_start_utc).total_seconds())

    return max(0, base - paused)


def reset_all() -> None:
    # Force widgets to rebuild fresh
    st.session_state.reset_counter += 1

    # Clear widget-backed keys safely
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

# ============================================================
# HEADER
# ============================================================
_, center, _ = st.columns([1, 1, 1])
with center:
    st.image(LOGO_PATH, width=90)

st.markdown(
    "<h1 style='text-align:center;margin-top:10px;'>"
    "Logistics Support Task Tracker</h1>",
    unsafe_allow_html=True,
)

if st.session_state.uploaded:
    st.toast("Upload Successful", icon="✅")
    st.session_state.uploaded = False


# ============================================================
# USER + TASK SELECTION
# ============================================================
user_login = get_os_user()
user_display = user_login.capitalize()
user_key = sanitize_key(user_login)

inputs_locked = st.session_state.state != "idle"

st.text_input("User", value=user_display, disabled=True)

tasks_df = load_tasks(TASKS_CSV)

task_name = st.selectbox(
    "Task name",
    [""] + sorted(tasks_df["TaskName"].unique().tolist()),
    disabled=inputs_locked,
    key=f"task_{st.session_state.reset_counter}",
)

if not task_name:
    st.info("Select a task to begin.")


# ============================================================
# CADENCE
# ============================================================
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
    with col:
        if st.button(
            cadence,
            disabled=(
                inputs_locked
                or not task_name
                or cadence not in available_cadences
            ),
            type="primary" if st.session_state.selected_cadence == cadence else "secondary",
            key=f"cad_{cadence}_{st.session_state.reset_counter}",
        ):
            st.session_state.selected_cadence = cadence
            st.rerun()


# ============================================================
# ACCOUNT + NOTES
# ============================================================
selected_account = st.selectbox(
    "Account (optional)",
    [""] + load_accounts(ACCOUNTS_XLSX),
    disabled=inputs_locked,
    key=f"acct_{st.session_state.reset_counter}",
)

st.text_area(
    "Notes (optional)",
    key="notes",
    height=120,
)


# ============================================================
# TIMER
# ============================================================
if st.session_state.state == "running":
    st_autorefresh(interval=1000, key="timer")

st.session_state.elapsed_seconds = compute_elapsed_seconds()
st.subheader("Task Control")

left, right = st.columns(2)

with left:
    if st.session_state.state == "idle":
        can_start = bool(task_name and st.session_state.selected_cadence)
        if st.button("Start", disabled=not can_start):
            st.session_state.state = "running"
            st.session_state.start_utc = now_utc()
            st.rerun()
    else:
        st.metric("Elapsed Time", format_hhmmss(st.session_state.elapsed_seconds))

with right:
    if st.session_state.state == "running":
        if st.button("Pause"):
            st.session_state.state = "paused"
            st.session_state.pause_start_utc = now_utc()
            st.rerun()

    elif st.session_state.state == "paused":
        if st.button("Resume"):
            st.session_state.paused_seconds += int(
                (now_utc() - st.session_state.pause_start_utc).total_seconds()
            )
            st.session_state.pause_start_utc = None
            st.session_state.state = "running"
            st.rerun()

    if st.session_state.state in ["running", "paused"]:
        if st.button("End"):
            st.session_state.state = "ended"
            st.session_state.end_utc = now_utc()
            st.rerun()


# ============================================================
# UPLOAD
# ============================================================
if st.session_state.state == "ended":
    st.divider()
    u, r = st.columns(2)

    with u:
        if st.button("Upload"):
            record = {
                "TaskID": str(uuid.uuid4()),
                "UserLogin": user_login,
                "UserDisplayName": user_display,
                "TaskName": task_name,
                "TaskCadence": st.session_state.selected_cadence,
                "CompanyGroup": selected_account or None,
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

    with r:
        if st.button("Reset"):
            reset_all()
            st.rerun()


# ============================================================
# FOOTER
# ============================================================
st.caption(f"Data path: {ROOT_DATA_DIR}\AllTasks")
st.caption(f"App version: {APP_VERSION}")