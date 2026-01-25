"""
app.py

Purpose:
    Landing page for the Logistics Support Streamlit suite.
    Styled to match Task Tracker and provides working navigation.
"""

import streamlit as st
from pathlib import Path
import config
import base64
import getpass
import pandas as pd

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Logistics Support App",
    layout="wide",
)

# ============================================================
# GLOBAL STYLING (MATCH TASK TRACKER — SAFE FOR SIDEBAR)
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

    /* Hide footer only (KEEP HEADER FOR SIDEBAR TOGGLE) */
    footer {visibility: hidden;}

    .block-container {
        padding-top: 1rem;
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

    .app-card {
        border: 1px solid #E6E6E6;
        border-radius: 12px;
        padding: 18px 20px;
        background-color: #FFFFFF;
        transition: box-shadow 0.15s ease-in-out;
    }

    .app-card:hover {
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    }

    .app-title {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 6px;
    }

    .app-desc {
        color: #6b6b6b;
        font-size: 14px;
        margin-bottom: 14px;
    }
    </style>
    """

st.markdown(get_global_css(), unsafe_allow_html=True)

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
# HEADER
# ============================================================

LOGO_PATH           = config.LOGO_PATH
logo_b64 = get_logo_base64(str(LOGO_PATH))

st.markdown(
    f"""
    <div class="header-row">
        <img class="header-logo" src="data:image/png;base64,{logo_b64}" />
        <h1 class="header-title">Logistics Support</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# ============================================================
# APPLICATION CARDS (REAL NAVIGATION)
# ============================================================
st.subheader("Tasks", anchor=False)

spacer_l, col1, space_m, col2, spacer_r = st.columns([0.4, 2, 0.4, 2, 0.4])

with col1:
    st.page_link(
        "pages/task-tracker.py",
        label="**Tracker**",
        
        icon="🕒",
    )

    st.caption(
        "Log daily operational tasks, track elapsed time, manage task cadence, "
        "and view live activity from other Logistics Support team members in real time."
    )

with col2:
    st.page_link(
        "pages/task-tracker-analytics.py",
        label="**Tracker**",
        
        icon="📊",
    )

    st.caption(
        "Upcoming logistics and analytics tools designed to support reporting, "
        "automation, and operational visibility."
    )

st.divider()

st.caption(
    "Use the sidebar to switch between applications at any time.",
    text_alignment="center",
)