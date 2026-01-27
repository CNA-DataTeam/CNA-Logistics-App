"""
address_validation_results.py

Purpose:
    Streamlit page for reviewing FedEx Address Validation results and emailing FedEx.

Behavior:
    - Loads results.xlsx from configured output path
    - Displays results in a selectable table
    - Allows user to select one or more rows
    - Opens a pre-filled Outlook email addressed to FedEx with row details
    - Preserves global app styling and layout conventions

Inputs:
    - results.xlsx (path resolved via config)

Outputs:
    - Outlook email draft (via win32com if available, otherwise mailto fallback)
"""

# ============================================================
# IMPORTS
# ============================================================
from pathlib import Path
from typing import List
import urllib.parse
import webbrowser

import pandas as pd
import streamlit as st

import config
import utils


# ============================================================
# PAGE CONFIG (MUST BE FIRST STREAMLIT CALL)
# ============================================================
st.set_page_config(
    page_title="FedEx Address Validator",
    layout="wide",
)


# ============================================================
# GLOBAL STYLING / HEADER
# ============================================================
st.markdown(utils.get_global_css(), unsafe_allow_html=True)

LOGO_PATH = config.LOGO_PATH
logo_b64 = utils.get_logo_base64(str(LOGO_PATH))

st.markdown(
    f"""
    <div class="header-row">
        <img class="header-logo" src="data:image/png;base64,{logo_b64}" />
        <h1 class="header-title">LS - FedEx Address Validator</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()


# ============================================================
# CONFIGURATION
# ============================================================
FEDEX_EMAIL_TO = ""  # quickresponse6@fedex.com
EMAIL_SUBJECT = "Clark National Accounts - Residential Status Dispute"

TABLE_KEY = "results_table"


# ============================================================
# CACHED DATA LOADING
# ============================================================
@st.cache_data
def load_results(file_path: Path) -> pd.DataFrame:
    """Load results file with caching to prevent reloading on every interaction."""
    return pd.read_excel(file_path, dtype=str)

# ============================================================
# LOAD RESULTS
# ============================================================
RESULTS_FILE: Path = config.ADDRESS_VALIDATION_RESULTS_FILE

if not RESULTS_FILE.exists():
    st.error(f"Results file not found:\n{RESULTS_FILE}")
    st.stop()

df = load_results(RESULTS_FILE)

if df.empty:
    st.info("No results available.")
    st.stop()

# ============================================================
# EMAIL BODY BUILDER
# ============================================================
def build_email_body(rows: pd.DataFrame) -> str:
    lines: List[str] = [
        "Hello FedEx Team,",
        "",
        "Please review the following address validation results:",
        "",
    ]

    for _, r in rows.iterrows():
        lines.extend(
            [
                f"Tracking Number: {r.get('Tracking Number', '')}",
                f"Invoice Number: {r.get('InvoiceNumber', '')}",
                f"Classification: {r.get('Residential Match', '')}",
                "Validated Address:",
                f"  {r.get('City', '')}, {r.get('StateOrProvince', '')}",
                "-" * 60,
            ]
        )

    lines.extend(["", "Thank you,"])
    return "\n".join(lines)

# ============================================================
# EMAIL DISPATCH (OUTLOOK OR FALLBACK)
# ============================================================
def open_email(to_addr: str, subject: str, body: str) -> None:
    try:
        import win32com.client as win32  # type: ignore

        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = to_addr
        mail.Subject = subject
        mail.Body = body
        mail.Display()

    except ModuleNotFoundError:
        params = {
            "subject": subject,
            "body": body,
        }
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        webbrowser.open(f"mailto:{to_addr}?{query}")

# ============================================================
# COLUMN FILTERING AND RENAMING
# ============================================================
# Convert InvoiceDate format if it exists (from yyyymmdd to mm/dd/yyyy)
if "InvoiceDate" in df.columns:
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], format="%Y%m%d", errors="coerce").dt.strftime("%m/%d/%Y")

# Remove unwanted columns (InvoiceDate is now kept and converted)
columns_to_remove = [
    "StreetLine1",
    "StreetLine2", 
    "PostalCode",
    "Shipment Date",
    "OriginalCustomerReference",
    "ID"
]

# Also remove all columns with "Recipient" in the name
columns_to_remove.extend([col for col in df.columns if "Recipient" in col or "recipient" in col])

# Drop columns that exist in the dataframe
df = df.drop(columns=[col for col in columns_to_remove if col in df.columns])

# Rename columns
df = df.rename(columns={
    "InvTrackingNumber": "Tracking Number",
    "ResidentialStatusMatch": "Residential Match"
})

# ============================================================
# FILTERS
# ============================================================
with st.expander("Filters", expanded=False):
    status_filter = st.multiselect(
        "Residential Status",
        sorted(df["Residential Match"].dropna().unique().tolist()),
    )

view_df = df
if status_filter:
    view_df = view_df[view_df["Residential Match"].isin(status_filter)]


# ============================================================
# INITIALIZE SESSION STATE FOR SELECTIONS
# ============================================================
if "select_all" not in st.session_state:
    st.session_state.select_all = False


# ============================================================
# TOGGLE SELECT / SEND EMAIL BUTTONS
# ============================================================
col1, col2, col3 = st.columns([1.5, 10, 1.69])

with col1:
    # Determine button label based on current state
    if st.session_state.select_all:
        button_label = "Deselect All ❌"
    else:
        button_label = "Select All ✅"
    
    if st.button(button_label, key="toggle_select"):
        # Toggle the selection state
        st.session_state.select_all = not st.session_state.select_all
        st.rerun()

# col2 is empty spacer in the middle

with col3:
    # This will be populated after we know selected_rows
    email_button_placeholder = st.empty()

# ============================================================
# TABLE WITH CHECKBOX SELECTION
# ============================================================

display_df = view_df.copy()

# Add checkbox column with Select All state
if "Select" not in display_df.columns:
    display_df.insert(0, "Select", st.session_state.select_all)
else:
    display_df["Select"] = st.session_state.select_all

edited_df = st.data_editor(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=700,
    key="address_validation_editor",
    column_config={
        "Select": st.column_config.CheckboxColumn(
            "Select",
            help="Select rows to include in the email",
        )
    },
    disabled=[c for c in display_df.columns if c != "Select"],
)

# Reset select_all flag after user interacts with table
# This allows individual selections after using Select All
if st.session_state.select_all and edited_df["Select"].sum() != len(edited_df):
    st.session_state.select_all = False

# ============================================================
# SELECTION EXTRACTION
# ============================================================
selected_rows = edited_df[edited_df["Select"]].drop(columns=["Select"])

# ============================================================
# SEND EMAIL BUTTON (in right column)
# ============================================================
with email_button_placeholder:
    send_email_clicked = st.button(
        "Send Email to FedEx 📨",
        disabled=selected_rows.empty,
        key="send_email",
    )

if send_email_clicked:
    email_body = build_email_body(selected_rows)
    open_email(FEDEX_EMAIL_TO, EMAIL_SUBJECT, email_body)
    st.success("Email draft opened. Please review before sending.")

# ============================================================
# FOOTNOTE
# ============================================================
st.caption(
    "Emails open as drafts in Outlook when available, otherwise in your default mail client."
)