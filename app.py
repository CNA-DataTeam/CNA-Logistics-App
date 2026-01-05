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

    @keyframes blink {
        50% {
            opacity: 0;
        }
    }

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

    .blink-colon {
        animation: blink 1s steps(1, start) infinite;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# PATH RESOLUTION (ONE LINER, NO DRAMA)
# ============================================================
def get_os_user() -> str:
    return os.getenv("USERNAME") or os.getenv("USER") or "unknown"


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


def format_hhmm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"

def format_hh_mm_parts(seconds: int) -> tuple[str, str]:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}", f"{m:02d}"

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
        root / "AllTasks"
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
    "uploaded": False,
    "confirm_open": False,
}

for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v

timer_placeholder = st.empty()

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
    st.session_state.reset_counter += 1
    st.session_state.pop("notes", None)

    st.session_state.state = "idle"
    st.session_state.start_utc = None
    st.session_state.end_utc = None
    st.session_state.pause_start_utc = None
    st.session_state.paused_seconds = 0
    st.session_state.elapsed_seconds = 0
    st.session_state.selected_cadence = None
    st.session_state.last_task_name = ""


def build_task_record(user_login, user_display, task_name, cadence, account, notes):
    return {
        "TaskID": str(uuid.uuid4()),
        "UserLogin": user_login,
        "UserDisplayName": user_display,
        "TaskName": task_name,
        "TaskCadence": cadence,
        "CompanyGroup": account or None,
        "Notes": notes.strip() if notes and notes.strip() else None,
        "StartTimestampUTC": st.session_state.start_utc,
        "EndTimestampUTC": st.session_state.end_utc,
        "DurationSeconds": int(st.session_state.elapsed_seconds),
        "UploadTimestampUTC": now_utc(),
        "AppVersion": APP_VERSION,
    }


# ============================================================
# HEADER
# ============================================================
_, center, _ = st.columns([1, 1, 1])
with center:
    st.image(LOGO_PATH, width=90)

st.markdown(
    "<h1 style='text-align:center;margin-top:10px;'>Logistics Support Task Tracker</h1>",
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
    is_selected = st.session_state.selected_cadence == cadence
    is_locked = st.session_state.state != "idle"

    disabled = (
        not task_name
        or cadence not in available_cadences
        or (is_locked and not is_selected)
    )

    with col:
        if st.button(
            cadence,
            disabled=disabled,
            type="primary" if is_selected else "secondary",
            key=f"cad_{cadence}_{st.session_state.reset_counter}",
        ):
            # Allow change only before the timer starts
            if not is_locked:
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

st.text_area("Notes (optional)", key="notes", height=120)

# ============================================================
# TIMER / TASK CONTROL
# ============================================================
if st.session_state.state == "running":
    with timer_placeholder:
        st_autorefresh(interval=60_000, key="timer")

st.session_state.elapsed_seconds = compute_elapsed_seconds()

st.subheader("Task Control")

left, right = st.columns(2)

with left:
    hh, mm = format_hh_mm_parts(st.session_state.elapsed_seconds)

    is_running = st.session_state.state == "running"
    colon_class = "blink-colon" if is_running else ""

    st.markdown(
        f"""
        <div style="text-align:center;">
            <div style="font-size:32px; font-weight:600;">
                {hh}<span class="{colon_class}">:</span>{mm}
            </div>
            <div style="font-size:12px; color:#6b6b6b;">
                Elapsed Time
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with right:
    # START (idle)
    if st.session_state.state == "idle":
        can_start = bool(task_name and st.session_state.selected_cadence)
        if st.button("Start", disabled=not can_start):
            st.session_state.state = "running"
            st.session_state.start_utc = now_utc()
            st.rerun()

    # PAUSE (running)
    elif st.session_state.state == "running":
        if st.button("Pause"):
            st.session_state.state = "paused"
            st.session_state.pause_start_utc = now_utc()
            st.rerun()

    # RESUME (paused)
    elif st.session_state.state == "paused":
        if st.button("Resume"):
            st.session_state.paused_seconds += int(
                (now_utc() - st.session_state.pause_start_utc).total_seconds()
            )
            st.session_state.pause_start_utc = None
            st.session_state.state = "running"
            st.rerun()

    # END (running or paused)
    if st.session_state.state in ["running", "paused"]:
        if st.button("End"):
            st.session_state.state = "ended"
            st.session_state.end_utc = now_utc()
            st.rerun()

# ============================================================
# CONFIRMATION MODAL
# ============================================================
@st.dialog("Submit?")
def confirm_submit():
    summary = pd.DataFrame(
        [
            ("User", user_display),
            ("Task Name", task_name),
            ("Cadence", st.session_state.selected_cadence),
            ("Time", format_hhmm(st.session_state.elapsed_seconds)),
            ("Account", selected_account),
            ("Notes", st.session_state.notes),
        ],
        columns=["Field", "Value"],
    )

    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        column_config={
            "Field": st.column_config.TextColumn(
                "Field",
                width="small"
            ),
            "Value": st.column_config.TextColumn(
                "Value",
                width="large"
            ),
        },
    )

    left, right = st.columns(2)

    with left:
        if st.button("Submit", type="primary", width="stretch"):
            record = build_task_record(
                user_login,
                user_display,
                task_name,
                st.session_state.selected_cadence,
                selected_account,
                st.session_state.notes,
            )

            df = pd.DataFrame([record])
            out_dir = build_out_dir(ROOT_DATA_DIR, user_key, st.session_state.start_utc)

            fname = f"task_{st.session_state.start_utc:%Y%m%d_%H%M%S}_{record['TaskID'][:8]}.parquet"
            atomic_write_parquet(df, out_dir / fname)

            st.session_state.uploaded = True
            st.session_state.confirm_open = False
            reset_all()
            st.rerun()

    with right:
        if st.button("Cancel", width="stretch"):
            st.session_state.confirm_open = False
            st.rerun()


# ============================================================
# UPLOAD / RESET
# ============================================================
if st.session_state.state == "ended":
    st.divider()

    u, r = st.columns(2)

    with u:
        if st.button("Upload"):
            st.session_state.confirm_open = True
            st.rerun()

    with r:
        if st.button("Reset"):
            reset_all()
            st.rerun()

# Open confirmation modal if requested
if st.session_state.confirm_open:
    confirm_submit()


# ============================================================
# FOOTER
# ============================================================
st.caption(f"\n\nApp version: {APP_VERSION}")