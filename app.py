from dotenv import load_dotenv

load_dotenv()

import base64
import csv
import html
import io
import json
import os
import re
import time
from pathlib import Path

import openai
import pandas as pd
import streamlit as st

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"
PREVIEW_ROWS = 10
MAX_CHATS = 10
MAX_CSV_CHARS = 120_000
MARK_PATH = Path(__file__).resolve().parent / "assets" / "heidelberg-mark.png"
USER_AVATAR = "🧑‍💼"
ASSISTANT_AVATAR = str(MARK_PATH)
RECORD_FOCUS_ALL = "All records"
FOCUS_COLUMN_NAMES = (
    "subject",
    "account name",
)
TEST_DATA_FILENAME = "RMC appointments.csv"
APPOINTMENT_COLUMNS = (
    "Subject",
    "Regarding",
    "Start",
    "End",
    "Location",
    "Owner",
    "Status",
    "Description",
)
ACCOUNT_COLUMNS = (
    "Account Name",
    "Primary Contact",
    "Phone",
    "City",
    "Customer Type",
    "Plant",
    "Owner",
)
APPOINTMENT_OWNER = "Momchil"
ACCOUNT_OWNER = "Bulgaria"
CRM_ONLY_REFUSAL = "I can only provide insights based on the loaded CRM data."
STORE_DIR = Path(__file__).resolve().parent / ".chat_store"
STORE_STATE_PATH = STORE_DIR / "state.json"

SYSTEM_PROMPT = (
    "You are a highly capable, clear, and helpful AI data assistant for ready-mix concrete and cement sales. "
    "Your tone is professional, approachable, and structured—using bolding and bullet points for readability. \n"
    "When the data supports it, talk about the appointment, the company it regards, the contact, the plant, and the next step. \n"
    "Appointments.Regarding matches Accounts.Account Name. Use both tables when a question is about a meeting or that company. \n"
    "CRITICAL RULE: You must ONLY answer questions based on the provided uploaded data context. "
    "You are strictly forbidden from providing general knowledge, outside facts, or opinions. "
    "If the user asks a question that cannot be answered using the uploaded data, politely refuse "
    "and state exactly: 'I can only provide insights based on the loaded CRM data.'\n"
    "STYLE RULE: Prefer bullets, but add a short useful detail under each point when the data "
    "supports it (names, dates, amounts, status). Write like a sharp colleague, not a telegram. "
    "Skip greetings, recap, and closing questions. Do not pad. Do not be robotic one-liners either."
)

SUMMARY_PROMPT = (
    "Summarize the ready-mix appointments and the accounts they regard. "
    "Use about 6–10 bullets covering upcoming and completed meetings, the companies, "
    "plants, and what each meeting is for. Each bullet can include one short supporting line."
)


def record_summary_prompt(record: str) -> str:
    return (
        f'Brief this appointment only: "{record}". '
        "Include the company in Regarding and the matching account (contact, city, plant, customer type). "
        "Cover status, time, location, what the meeting is for, and the next action."
    )


NEXT_STEPS_PROMPT = (
    "Top 5 next steps as a ready-mix salesperson, ranked by urgency. "
    "Use the appointments and the related accounts. "
    "For each: the action, which meeting or company it relates to, and a brief why from the data."
)

MEETING_PREP_SYSTEM = (
    "You prepare meeting briefings from CRM assistant chats and uploaded CRM data only. "
    "Never use general knowledge or invent facts. If something is not in the data or chat, "
    f"omit it or state exactly: {CRM_ONLY_REFUSAL} "
    "Be usable and specific: names, dates, amounts, status. Not fluffy."
)

APP_CSS = """
<style>
:root {
    --hm-green: #004E2B;
    --hm-green-dark: #003820;
    --hm-green-soft: #e7f2eb;
    --hm-leaf: #00DD39;
    --hm-bar-h: 56px;
    --hm-canvas: #f3f2f1;
    --hm-border: #e1dfdd;
    --hm-text: #201f1e;
    --hm-muted: #605e5c;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    display: none !important;
    height: 0 !important;
}
[data-testid="stToolbar"] {display: none !important;}
[data-testid="stDecoration"] {display: none !important;}
.stDeployButton {display: none !important;}
#stDecoration {display: none !important;}

html, body, .stApp {
    font-family: "Segoe UI", "Segoe UI Variable", "Segoe UI Web (West European)", system-ui, sans-serif;
    color: var(--hm-text);
}

.stApp {
    background: var(--hm-canvas);
}

.hm-bar,
.hm-stage,
.hm-empty,
.hm-nav-label,
.hm-crumb,
.hm-title,
.hm-sub {
    font-family: "Segoe UI", "Segoe UI Variable", "Segoe UI Web (West European)", system-ui, sans-serif;
}

div[data-testid="stElementContainer"]:has(.hm-bar),
div.element-container:has(.hm-bar) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
}

.hm-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: var(--hm-bar-h);
    background: var(--hm-green);
    z-index: 1000001;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px 0 14px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
}

.hm-bar-left,
.hm-bar-right {
    display: flex;
    align-items: center;
    min-width: 190px;
    position: relative;
    z-index: 1;
}

.hm-bar-right {
    justify-content: flex-end;
}

.hm-mark {
    width: 40px;
    height: 40px;
    background: #ffffff;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 40px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
}

.hm-mark img {
    width: 34px;
    height: 34px;
    object-fit: contain;
    display: block;
}

.hm-app {
    color: #ffffff;
    font-size: 16px;
    font-weight: 600;
    margin-left: 12px;
    letter-spacing: 0.01em;
}

.hm-bar-title {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    color: #ffffff;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 0.012em;
    white-space: nowrap;
    pointer-events: none;
}

.hm-gear {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 14px;
    cursor: default;
}

.hm-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 32px;
}

[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid var(--hm-border) !important;
    padding-top: var(--hm-bar-h) !important;
    box-sizing: border-box !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: var(--hm-text);
    font-weight: 600;
}

.hm-nav-label {
    margin: 0.9rem 0 0.2rem 0.1rem;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--hm-muted);
}

.hm-stage {
    padding: 0.15rem 0 0.8rem 0;
    margin-bottom: 0.85rem;
    border-bottom: 1px solid var(--hm-border);
}

.hm-crumb {
    font-size: 12px;
    font-weight: 600;
    color: var(--hm-green);
    letter-spacing: 0.02em;
    margin: 0 0 0.2rem 0;
}

.hm-crumb span {
    color: #a19f9d;
    font-weight: 400;
    margin: 0 0.15rem;
}

.hm-title {
    margin: 0;
    font-size: 1.7rem;
    line-height: 1.2;
    font-weight: 600;
    color: var(--hm-text);
    letter-spacing: -0.02em;
}

.hm-sub {
    margin: 0.28rem 0 0 0;
    color: var(--hm-muted);
    font-size: 0.95rem;
}

.hm-empty {
    background: #ffffff;
    border: 1px solid var(--hm-border);
    border-left: 3px solid var(--hm-green);
    border-radius: 2px;
    padding: 1.05rem 1.15rem 1.1rem 1.1rem;
    margin: 0.15rem 0 0.35rem 0;
    box-shadow: 0 1.6px 3.6px rgba(0, 0, 0, 0.06), 0 0.3px 0.9px rgba(0, 0, 0, 0.04);
}

.hm-empty p {
    margin: 0 0 0.22rem 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--hm-text);
}

.hm-empty span {
    color: var(--hm-muted);
    font-size: 0.95rem;
}

[data-testid="stMainBlockContainer"],
[data-testid="stBottomBlockContainer"],
.block-container {
    max-width: none !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}

.block-container {
    padding-top: calc(var(--hm-bar-h) + 1.15rem) !important;
    padding-bottom: 1.25rem;
}

[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] {
    background: var(--hm-canvas);
}

[data-testid="stBottom"] {
    position: sticky;
    bottom: 0;
    z-index: 30;
    border-top: 1px solid var(--hm-border);
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 2px !important;
    border: 1px solid #c8c6c4 !important;
    background: #ffffff !important;
    color: #323130 !important;
    font-weight: 600 !important;
    box-shadow: none !important;
}

.stButton > button:hover:not(:disabled),
.stDownloadButton > button:hover {
    background: #f3f2f1 !important;
    border-color: var(--hm-green) !important;
    color: var(--hm-green) !important;
}

.stButton > button:disabled,
.stDownloadButton > button:disabled {
    opacity: 0.55 !important;
}

[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stDownloadButton > button {
    border: 1px solid transparent !important;
    background: transparent !important;
    color: #323130 !important;
    font-weight: 600 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    border-radius: 2px !important;
    padding-left: 0.55rem !important;
}

[data-testid="stSidebar"] .stButton > button:hover:not(:disabled),
[data-testid="stSidebar"] .stDownloadButton > button:hover {
    background: #f3f2f1 !important;
    border-color: transparent !important;
    color: var(--hm-green) !important;
}

[data-testid="stSidebar"] .st-key-new_chat button {
    background: var(--hm-green) !important;
    color: #ffffff !important;
    border: 1px solid var(--hm-green) !important;
    border-radius: 4px !important;
    min-height: 36px !important;
    font-weight: 600 !important;
    justify-content: center !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] .st-key-new_chat button > div {
    justify-content: center !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .st-key-new_chat button:hover:not(:disabled) {
    background: var(--hm-green-dark) !important;
    border-color: var(--hm-green-dark) !important;
    color: #ffffff !important;
}

.st-key-bar_home {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 196px !important;
    height: var(--hm-bar-h) !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 1000002 !important;
}

.st-key-bar_home .stButton,
.st-key-bar_home .stButton > button {
    width: 100% !important;
    height: 100% !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: transparent !important;
    cursor: pointer !important;
}

.st-key-bar_home .stButton > button * {
    color: transparent !important;
}

.st-key-bar_home .stButton > button:hover,
.st-key-bar_home .stButton > button:focus-visible {
    background: rgba(255, 255, 255, 0.09) !important;
    outline: none !important;
}

[data-testid="stSidebar"] .st-key-generate_test_data_side button {
    background: #ffffff !important;
    color: var(--hm-green) !important;
    border: 1px solid var(--hm-green) !important;
    border-radius: 4px !important;
    min-height: 36px !important;
    font-weight: 600 !important;
    justify-content: center !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] .st-key-generate_test_data_side button > div {
    justify-content: center !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .st-key-generate_test_data_side button:hover:not(:disabled) {
    background: var(--hm-green-soft) !important;
    border-color: var(--hm-green) !important;
    color: var(--hm-green-dark) !important;
}

[data-testid="stSidebar"] [class*="st-key-open_chat_"] button > div {
    justify-content: flex-start !important;
}

[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"]) {
    gap: 0 !important;
    align-items: center;
    border-radius: 4px;
    margin: 1px 0;
    background: transparent;
}

[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"]):hover {
    background: #f3f2f1;
}

[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"] button[data-testid="stBaseButton-primary"]),
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"] button[kind="primary"]) {
    background: var(--hm-green-soft);
    box-shadow: inset 3px 0 0 var(--hm-green);
}

[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"] button[data-testid="stBaseButton-primary"]):hover,
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-open_chat_"] button[kind="primary"]):hover {
    background: #dceadf;
}

[data-testid="stSidebar"] [class*="st-key-open_chat_"] button,
[data-testid="stSidebar"] [class*="st-key-open_chat_"] button[kind="primary"],
[data-testid="stSidebar"] [class*="st-key-open_chat_"] button[data-testid="stBaseButton-primary"] {
    text-align: left !important;
    justify-content: flex-start !important;
    border-radius: 4px !important;
    padding: 0.35rem 0.55rem !important;
    min-height: 36px !important;
    font-size: 0.92rem !important;
    font-weight: 400 !important;
    overflow: hidden;
    white-space: nowrap;
    background: transparent !important;
    border: 1px solid transparent !important;
    color: #323130 !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] [class*="st-key-open_chat_"] button:hover:not(:disabled) {
    background: transparent !important;
    border-color: transparent !important;
    color: var(--hm-text) !important;
}

[data-testid="stSidebar"] [class*="st-key-open_chat_"] button[kind="primary"],
[data-testid="stSidebar"] [class*="st-key-open_chat_"] button[data-testid="stBaseButton-primary"] {
    color: var(--hm-green) !important;
    font-weight: 600 !important;
}

[data-testid="stSidebar"] [class*="st-key-del_chat_"] button {
    padding: 0.2rem !important;
    min-width: 28px !important;
    min-height: 28px !important;
    width: 28px !important;
    border-radius: 4px !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    color: #8a8886 !important;
    justify-content: center !important;
}

[data-testid="stSidebar"] [class*="st-key-del_chat_"] button:hover:not(:disabled) {
    background: #fde7e9 !important;
    border-color: transparent !important;
    color: #a4262c !important;
}

.st-key-command_bar {
    position: fixed !important;
    position-anchor: --hm-main;
    left: 21.5rem !important;
    right: 1.5rem !important;
    left: anchor(left) !important;
    right: anchor(right) !important;
    bottom: 7.6rem !important;
    width: auto !important;
    max-width: none !important;
    z-index: 40 !important;
    box-sizing: border-box !important;
    margin: 0 !important;
    padding: 0.35rem 1.5rem 0.45rem !important;
    background: var(--hm-canvas) !important;
    border: none !important;
    box-shadow: none !important;
}

.stApp:not(:has(.crm-home)) [data-testid="stMain"] {
    anchor-name: --hm-main;
}

.stApp:not(:has(.crm-home)) [data-testid="stElementContainer"]:has(.st-key-command_bar),
.stApp:not(:has(.crm-home)) [data-testid="stLayoutWrapper"]:has(.st-key-command_bar) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
}

.stApp:not(:has(.crm-home)) .block-container {
    padding-bottom: 8rem !important;
}

.st-key-command_bar [data-testid="stSelectbox"] {
    min-width: 220px;
    max-width: 280px;
    background: #ffffff;
}

.st-key-focus_record_btn button {
    max-width: 280px;
}

.st-key-focus_record_btn button p {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.st-key-command_bar .stButton > button,
.st-key-command_bar .stDownloadButton > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    color: #323130 !important;
    font-weight: 600 !important;
    border-radius: 2px !important;
    box-shadow: none !important;
}

.st-key-command_bar .stButton > button:hover:not(:disabled),
.st-key-command_bar .stDownloadButton > button:hover {
    background: #f3f2f1 !important;
    border-color: transparent !important;
    color: var(--hm-green) !important;
}

.st-key-data_tools {
    background: #ffffff;
    border: 1px solid var(--hm-border);
    border-radius: 2px;
    padding: 0.55rem 0.75rem 0.15rem;
    margin: 0 0 0.85rem 0;
}

.st-key-data_tools [data-testid="stWidgetLabel"],
.st-key-data_tools [data-testid="stWidgetLabel"] p {
    font-weight: 700 !important;
}

.st-key-toggle_crm_tables {
    display: flex;
    justify-content: flex-end;
}

.st-key-toggle_crm_tables button {
    min-height: 30px !important;
    padding: 0 0.65rem !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}

[data-testid="stChatMessage"] {
    background: #ffffff;
    border: 1px solid var(--hm-border);
    border-radius: 2px;
    padding: 0.45rem 0.75rem 0.2rem 0.45rem;
    box-shadow: 0 1.6px 3.6px rgba(0, 0, 0, 0.06), 0 0.3px 0.9px rgba(0, 0, 0, 0.04);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    border-left: 3px solid var(--hm-green);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #faf9f8;
    border-left: 3px solid #8a8886;
}

[data-testid="stChatMessageAvatarAssistant"] img,
[data-testid="chatAvatarIcon-assistant"] img {
    border-radius: 6px;
}

.stChatInput textarea,
[data-testid="stChatInput"] textarea {
    border-radius: 2px !important;
    caret-color: var(--hm-green);
}

[data-testid="stChatInput"] > div {
    border-radius: 2px !important;
    border: 1px solid #c8c6c4 !important;
    background: #ffffff !important;
}

[data-testid="stExpander"] details {
    border: 1px solid var(--hm-border) !important;
    border-radius: 2px !important;
    background: #ffffff !important;
}

[data-testid="stCaptionContainer"] {
    color: var(--hm-muted);
}

.stApp a {
    color: var(--hm-green);
}
</style>
"""



def is_valid_api_key(api_key: str) -> bool:
    return bool(api_key) and api_key.strip() not in {"", "your_key_here"}


def dataframe_csv_for_prompt(df: pd.DataFrame) -> str:
    csv_text = df.to_csv(index=False)
    if len(csv_text) <= MAX_CSV_CHARS:
        return csv_text
    preview = df.head(200).to_csv(index=False)
    return (
        preview
        + "\n[The CSV above is a preview. The full dataset has "
        + f"{len(df)} rows. Answer from this preview plus the columns and shape.]\n"
    )


def find_focus_column(df: pd.DataFrame) -> str | None:
    lowered = {str(column).strip().lower(): column for column in df.columns}
    for name in FOCUS_COLUMN_NAMES:
        if name in lowered:
            return lowered[name]
    return None


def record_focus_options(df: pd.DataFrame) -> list[str]:
    column = find_focus_column(df)
    if column is None:
        return [RECORD_FOCUS_ALL]
    values = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
    )
    unique = sorted({value for value in values.tolist() if value}, key=str.lower)
    return [RECORD_FOCUS_ALL, *unique[:500]]


def focused_dataframe(df: pd.DataFrame, record: str | None) -> pd.DataFrame:
    if df is None or not record or record in {RECORD_FOCUS_ALL, "All Accounts"}:
        return df
    column = find_focus_column(df)
    if column is None:
        return df
    mask = df[column].astype(str).str.strip().str.lower() == record.strip().lower()
    focused = df.loc[mask]
    return focused if not focused.empty else df.iloc[0:0]


def related_accounts(
    appointments: pd.DataFrame | None,
    accounts: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if accounts is None or getattr(accounts, "empty", True):
        return accounts
    if appointments is None or getattr(appointments, "empty", True):
        return accounts.iloc[0:0]
    if "Regarding" not in appointments.columns or "Account Name" not in accounts.columns:
        return accounts
    names = {
        value.strip().lower()
        for value in appointments["Regarding"].dropna().astype(str).tolist()
        if value.strip()
    }
    mask = accounts["Account Name"].astype(str).str.strip().str.lower().isin(names)
    matched = accounts.loc[mask]
    return matched if not matched.empty else accounts.iloc[0:0]


def tables_for_focus(
    appointments: pd.DataFrame | None,
    accounts: pd.DataFrame | None,
    focus: str | None,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    focused = focused_dataframe(appointments, focus) if appointments is not None else None
    if accounts is None:
        return focused, None
    if not focus or focus in {RECORD_FOCUS_ALL, "All Accounts"}:
        return focused, accounts
    return focused, related_accounts(focused, accounts)


def crm_tables_text(appointments: pd.DataFrame | None, accounts: pd.DataFrame | None) -> str:
    sections: list[str] = []
    if appointments is not None:
        rows, cols = appointments.shape
        columns = ", ".join(str(col) for col in appointments.columns)
        sections.append(
            "Appointments (Regarding is the account this meeting is about):\n"
            f"Columns: {columns}\n"
            f"Shape: {rows} rows × {cols} columns\n\n"
            f"{dataframe_csv_for_prompt(appointments)}"
        )
    if accounts is not None and not getattr(accounts, "empty", True):
        rows, cols = accounts.shape
        columns = ", ".join(str(col) for col in accounts.columns)
        sections.append(
            "Accounts (join Account Name to Appointments.Regarding):\n"
            f"Columns: {columns}\n"
            f"Shape: {rows} rows × {cols} columns\n\n"
            f"{dataframe_csv_for_prompt(accounts)}"
        )
    return "\n".join(sections)


def build_user_prompt_with_data(question: str, df: pd.DataFrame) -> str:
    focus = st.session_state.get("focused_account") or RECORD_FOCUS_ALL
    appointments, accounts = tables_for_focus(df, st.session_state.get("active_accounts"), focus)
    rows = 0 if appointments is None else len(appointments)
    focus_line = (
        f"Record focus: {focus} ({rows} matching appointments). Use only these appointments and their accounts.\n"
        if focus not in {RECORD_FOCUS_ALL, "All Accounts"}
        else ""
    )
    return (
        f"{question}\n\n"
        "Answer with clear bullets and enough detail to be useful. "
        "One or two short sentences per point is fine. No greetings or wrap-up.\n"
        "If the question is about the company in a meeting, use the account whose Account Name equals Regarding.\n\n"
        "---\n"
        "CRM data context (use this as the only source of truth):\n"
        f"{focus_line}"
        f"{crm_tables_text(appointments, accounts)}"
    )


def next_steps_prompt(record: str | None = None) -> str:
    if record:
        return (
            f'Top 5 next steps for this specific record: "{record}", ranked by urgency. '
            "For each: the action, who/what it relates to, and a brief why from the data."
        )
    return NEXT_STEPS_PROMPT


def api_message_content(message: dict) -> str:
    return message.get("api_content", message["content"])


def build_api_messages(df: pd.DataFrame) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    last_user_index = max(
        (index for index, message in enumerate(st.session_state.messages) if message["role"] == "user"),
        default=None,
    )
    for index, message in enumerate(st.session_state.messages):
        if message["role"] == "user" and index == last_user_index:
            content = build_user_prompt_with_data(api_message_content(message), df)
        else:
            content = message["content"] if message["role"] == "assistant" else api_message_content(message)
            if message["role"] == "user":
                content = message["content"]
        messages.append({"role": message["role"], "content": content})
    return messages


def generate_chat_summary(api_key: str, messages: list[dict]) -> str:
    transcript = format_meeting_notes(messages)
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You summarize CRM assistant chats. Use clear bullets with a bit of "
                    "context so the notes are usable later. No greetings or wrap-up. "
                    "Capture what was asked and the key facts or answers."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Turn this chat into useful bullet points with brief supporting detail:\n\n"
                    f"{transcript}"
                ),
            },
        ],
        temperature=0.35,
        max_tokens=900,
    )
    return (response.choices[0].message.content or "").strip()


def generate_meeting_prep_pack(api_key: str, messages: list[dict], df: pd.DataFrame) -> str:
    transcript = format_meeting_notes(messages)
    focus = st.session_state.get("focused_account") or RECORD_FOCUS_ALL
    appointments, accounts = tables_for_focus(df, st.session_state.get("active_accounts"), focus)
    rows = 0 if appointments is None else len(appointments)
    focus_line = (
        f"Record focus: {focus} ({rows} matching appointments). Use only these appointments and their accounts.\n"
        if focus not in {RECORD_FOCUS_ALL, "All Accounts"}
        else ""
    )
    user_content = (
        "Create a meeting prep pack from this CRM chat and data.\n\n"
        "Output EXACTLY this structure with these headings, no title, no extra sections:\n\n"
        "BRIEF\n"
        "- bullets covering the situation, account/deal facts, and current status\n\n"
        "RISKS\n"
        "- bullets for blockers, overdue items, stalled deals, or missing info from the data\n\n"
        "NEXT STEPS\n"
        "1. action — who/what — why\n"
        "2. action — who/what — why\n"
        "3. action — who/what — why\n"
        "4. action — who/what — why\n"
        "5. action — who/what — why\n\n"
        "TALKING POINTS\n"
        "- first thing to say in the meeting\n"
        "- second thing to say\n"
        "- third thing to say\n\n"
        "NEXT STEPS must be exactly 5 numbered actions. TALKING POINTS must be exactly 3 bullets. "
        "Keep every line tied to the CRM data or chat. No greetings or wrap-up.\n\n"
        "---\n"
        "Chat transcript:\n"
        f"{transcript}\n\n"
        "---\n"
        "CRM data context (only source of truth):\n"
        f"{focus_line}"
        f"{crm_tables_text(appointments, accounts)}"
    )
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": MEETING_PREP_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.35,
        max_tokens=1200,
    )
    return (response.choices[0].message.content or "").strip()


def stream_chat_response(api_key: str, messages: list[dict]):
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    stream = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.35,
        max_tokens=900,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def run_chat_turn(prompt: str, df: pd.DataFrame, api_key: str, display: str | None = None) -> None:
    visible = display or prompt
    st.session_state.messages.append(
        {"role": "user", "content": visible, "api_content": prompt}
    )
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(visible)

    api_messages = build_api_messages(df)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        try:
            reply = st.write_stream(stream_chat_response(api_key, api_messages))
        except Exception as exc:
            reply = f"Could not complete that: {exc}"
            st.error(reply)

    assistant_message = {"role": "assistant", "content": reply}
    st.session_state.messages.append(assistant_message)
    st.session_state.chat_summary = None
    st.session_state.chat_summary_saved = False
    st.session_state.meeting_prep_pack = None
    st.session_state.meeting_prep_saved = False


def mark_data_uri() -> str:
    try:
        encoded = base64.b64encode(MARK_PATH.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{encoded}"


def render_top_bar() -> None:
    src = mark_data_uri()
    logo = (
        f'<img src="{src}" alt="Heidelberg Materials" draggable="false" />'
        if src
        else ""
    )
    st.markdown(
        f"""
        <div class="hm-bar">
          <div class="hm-bar-left">
            <div class="hm-mark">{logo}</div>
            <span class="hm-app">Sales@RMC</span>
          </div>
          <div class="hm-bar-title">Heidelberg Materials</div>
          <div class="hm-bar-right">
            <div class="hm-gear" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="20" height="20">
                <path fill="#ffffff" d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.2 7.2 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.59.22-1.14.54-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.71 8.84a.5.5 0 0 0 .12.64l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32c.13.22.39.31.6.22l2.39-.96c.49.4 1.04.72 1.63.94l.36 2.54c.04.24.25.42.5.42h3.84c.25 0 .46-.18.5-.42l.36-2.54c.59-.22 1.14-.54 1.63-.94l2.39.96c.22.09.47 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"/>
              </svg>
            </div>
            <div class="hm-avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18">
                <circle cx="12" cy="8.5" r="3.1" fill="#004E2B"></circle>
                <path d="M5.2 18.6c1.35-2.55 3.7-3.85 6.8-3.85s5.45 1.3 6.8 3.85" fill="none" stroke="#004E2B" stroke-width="1.7" stroke-linecap="round"></path>
              </svg>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Invisible click target laid over the logo + "Sales@RMC" sign. Demo only.
    if st.button("Sales@RMC", key="bar_home", type="tertiary"):
        st.session_state.demo_view = "home"
        st.rerun()


def workspace_subtitle(df: pd.DataFrame | None, ai_df: pd.DataFrame | None) -> str:
    if df is None:
        return "Generate test data on the left, then ask about a pour, a plant, or the next call."
    name = st.session_state.filename or "CRM data"
    accounts = st.session_state.get("active_accounts")
    account_count = 0 if accounts is None else len(accounts)
    focus = st.session_state.focused_account or RECORD_FOCUS_ALL
    if focus in {RECORD_FOCUS_ALL, "All Accounts"}:
        return f"{name}  ·  {len(df):,} appointments  ·  {account_count:,} accounts"
    matched = 0 if ai_df is None else len(ai_df)
    return f"{name}  ·  {focus}  ·  {matched:,} appointments"


def render_workspace_header(df: pd.DataFrame | None, ai_df: pd.DataFrame | None) -> None:
    subtitle = html.escape(workspace_subtitle(df, ai_df))
    st.markdown(
        f"""
        <div class="hm-stage">
          <div class="hm-crumb">Sales@RMC <span>/</span> Assistant</div>
          <div class="hm-title">CRM Assistant</div>
          <p class="hm-sub">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


DEMO_HOME_CSS = """
<style>
.stApp:has(.crm-home) [data-testid="stSidebar"],
.stApp:has(.crm-home) [data-testid="stSidebarCollapsedControl"],
.stApp:has(.crm-home) [data-testid="collapsedControl"] {
    display: none !important;
    width: 0 !important;
    min-width: 0 !important;
}
.stApp:has(.crm-home) [data-testid="stMainBlockContainer"],
.stApp:has(.crm-home) .block-container {
    padding: 0 !important;
    max-width: none !important;
}
.stApp:has(.crm-home),
.stApp:has(.crm-home) [data-testid="stAppViewContainer"],
.stApp:has(.crm-home) [data-testid="stMain"] {
    background: #E7EEEA !important;
    overflow: hidden !important;
    height: 100vh !important;
}
.stApp:has(.crm-home) [data-testid="stElementContainer"]:has(.crm-top),
.stApp:has(.crm-home) .element-container:has(.crm-top) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
}
.stApp:has(.crm-home) .st-key-crm_nav {
    position: fixed !important;
    top: 60px;
    left: 0;
    width: 248px;
    height: calc(100vh - 60px);
    z-index: 40;
    box-sizing: border-box;
    background: #F6F8F7;
    border-right: 1px solid #D5DED8;
    padding: 18px 12px 28px !important;
    overflow: auto;
    gap: 0 !important;
}
.stApp:has(.crm-home) .st-key-crm_nav [data-testid="stVerticalBlock"],
.stApp:has(.crm-home) .st-key-crm_nav [data-testid="stElementContainer"],
.stApp:has(.crm-home) .st-key-crm_nav .element-container,
.stApp:has(.crm-home) .st-key-crm_nav [data-testid="stMarkdown"],
.stApp:has(.crm-home) .st-key-crm_nav [data-testid="stMarkdown"] p {
    gap: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}
.crm-top {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 60px;
    z-index: 50;
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 0 18px 0 16px;
    background: #0E6242;
    box-shadow: 0 1px 0 rgba(0, 0, 0, 0.18);
    font-family: "Segoe UI", "Segoe UI Variable", system-ui, sans-serif;
    overflow: hidden;
}
.crm-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 0 0 auto;
}
.crm-logo {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 36px;
}
.crm-logo img {
    width: 30px;
    height: 30px;
    object-fit: contain;
    display: block;
}
.crm-brand-name {
    color: #ffffff;
    font-size: 15px;
    font-weight: 650;
    letter-spacing: 0.01em;
    white-space: nowrap;
}
.crm-brand-chip {
    color: #E7F6EE;
    background: rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
}
.crm-search {
    margin-left: auto;
    flex: 1 1 180px;
    max-width: 420px;
    min-width: 0;
    height: 36px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.16);
    color: rgba(255, 255, 255, 0.86);
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 14px;
    font-size: 13.5px;
    overflow: hidden;
    white-space: nowrap;
}
.crm-search svg,
.crm-util svg {
    width: 16px;
    height: 16px;
    flex: 0 0 16px;
}
.crm-utils {
    display: flex;
    align-items: center;
    gap: 8px;
}
.crm-util {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
}
.crm-avatar {
    width: 34px;
    height: 34px;
    margin-left: 4px;
    border-radius: 9px;
    background: #E7F6EE;
    color: #0E6242;
    font-size: 12px;
    font-weight: 750;
    display: flex;
    align-items: center;
    justify-content: center;
    letter-spacing: 0.04em;
}
.crm-stage {
    position: fixed;
    top: 60px;
    left: 248px;
    right: 0;
    bottom: 0;
    padding: 16px 18px 18px;
    box-sizing: border-box;
    background: #E7EEEA;
    font-family: "Segoe UI", "Segoe UI Variable", system-ui, sans-serif;
    color: #1C2823;
}
.crm-panel {
    background: #ffffff;
    border: 1px solid #D5DED8;
    border-radius: 12px;
    min-height: calc(100vh - 94px);
    box-shadow: 0 8px 24px rgba(20, 48, 34, 0.04);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.crm-tools {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 16px;
    border-bottom: 1px solid #E4EBE6;
}
.crm-tools-left,
.crm-tools-right {
    display: flex;
    align-items: center;
    gap: 6px;
}
.crm-tool {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #3C4A44;
    font-size: 13.5px;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 8px;
    cursor: default;
    user-select: none;
    white-space: nowrap;
}
.crm-tool svg {
    width: 15px;
    height: 15px;
}
.crm-filter {
    margin-left: 8px;
    min-width: 180px;
    height: 32px;
    border: 1px solid #D5DED8;
    border-radius: 8px;
    color: #8A9790;
    font-size: 13px;
    display: flex;
    align-items: center;
    padding: 0 10px;
    background: #FBFCFB;
}
.crm-viewhead {
    padding: 16px 18px 8px;
}
.crm-viewhead h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 650;
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
}
.crm-viewhead h1 svg {
    width: 16px;
    height: 16px;
    color: #5E6E66;
}
.crm-cols {
    display: grid;
    grid-template-columns: 1.4fr 1fr 0.9fr 1fr 0.8fr;
    gap: 12px;
    margin: 8px 18px 0;
    padding: 0 4px 10px;
    border-bottom: 1px solid #E4EBE6;
    color: #5C6B64;
    font-size: 13px;
    font-weight: 650;
}
.crm-cols span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.crm-cols svg {
    width: 14px;
    height: 14px;
    flex: 0 0 14px;
}
.crm-empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 24px 16px 80px;
}
.crm-empty-mark {
    width: 132px;
    height: 132px;
    border-radius: 50%;
    background: #DCEADF;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 18px;
}
.crm-empty-mark svg {
    width: 64px;
    height: 64px;
}
.crm-empty p {
    margin: 0;
    font-size: 16px;
    font-weight: 650;
    color: #1C2823;
}
.crm-empty span {
    display: block;
    margin-top: 6px;
    color: #66756D;
    font-size: 14px;
}
.crm-kicker {
    margin: 16px 10px 6px;
    font-size: 11px;
    font-weight: 750;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6D7C74;
    font-family: "Segoe UI", "Segoe UI Variable", system-ui, sans-serif;
}
.crm-link {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 38px;
    padding: 0 10px;
    border-radius: 9px;
    color: #24312C;
    font-size: 14.5px;
    font-weight: 500;
    cursor: default;
    user-select: none;
    font-family: "Segoe UI", "Segoe UI Variable", system-ui, sans-serif;
}
.crm-link svg {
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
}
.crm-link.is-on {
    background: #E3F2E9;
    color: #0E6242;
    box-shadow: inset 3px 0 0 #0E6242;
}
.stApp:has(.crm-home) .st-key-crm_open_chat,
.stApp:has(.crm-home) [data-testid="stElementContainer"]:has(.st-key-crm_open_chat) {
    height: 38px !important;
    min-height: 0 !important;
    max-height: 38px !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
.stApp:has(.crm-home) .st-key-crm_nav [data-testid="stElementContainer"].st-key-crm_open_chat {
    margin-top: 14px !important;
    margin-bottom: 0 !important;
}
.stApp:has(.crm-home) .st-key-crm_open_chat button {
    width: 100% !important;
    height: 38px !important;
    min-height: 38px !important;
    max-height: 38px !important;
    padding: 0 10px !important;
    border: 1px solid transparent !important;
    border-radius: 9px !important;
    background: transparent !important;
    color: #24312C !important;
    box-shadow: none !important;
    outline: none !important;
    font-size: 14.5px !important;
    font-weight: 500 !important;
    font-family: "Segoe UI", "Segoe UI Variable", system-ui, sans-serif !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    gap: 10px !important;
    transform: none !important;
}
.stApp:has(.crm-home) .st-key-crm_open_chat button::before {
    content: "";
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    background: #24312C;
    -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M5.2 6.4A2.2 2.2 0 0 1 7.4 4.2h9.2A2.2 2.2 0 0 1 18.8 6.4v5.6a2.2 2.2 0 0 1-2.2 2.2H9.1L5.6 17.4c-.45.38-1.1.04-1.1-.5V6.4z'/%3E%3C/svg%3E") center / contain no-repeat;
    mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M5.2 6.4A2.2 2.2 0 0 1 7.4 4.2h9.2A2.2 2.2 0 0 1 18.8 6.4v5.6a2.2 2.2 0 0 1-2.2 2.2H9.1L5.6 17.4c-.45.38-1.1.04-1.1-.5V6.4z'/%3E%3C/svg%3E") center / contain no-repeat;
}
.stApp:has(.crm-home) .st-key-crm_open_chat button p,
.stApp:has(.crm-home) .st-key-crm_open_chat button div,
.stApp:has(.crm-home) .st-key-crm_open_chat button span {
    text-align: left !important;
    justify-content: flex-start !important;
    margin: 0 !important;
}
.stApp:has(.crm-home) .st-key-crm_open_chat button:hover:not(:disabled),
.stApp:has(.crm-home) .st-key-crm_open_chat button:focus,
.stApp:has(.crm-home) .st-key-crm_open_chat button:focus-visible {
    background: transparent !important;
    border-color: transparent !important;
    box-shadow: none !important;
    outline: none !important;
    color: #0E6242 !important;
    font-weight: 700 !important;
}
.stApp:has(.crm-home) .st-key-crm_open_chat button:hover:not(:disabled)::before,
.stApp:has(.crm-home) .st-key-crm_open_chat button:focus::before {
    background: #0E6242;
}
</style>
"""


def _crm_icon(body: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{body}</svg>'
    )


def _crm_link(icon: str, label: str, current: bool = False) -> str:
    kind = "crm-link is-on" if current else "crm-link"
    return f'<div class="{kind}">{icon}<span>{html.escape(label)}</span></div>'


def render_demo_home() -> None:
    # Temporary demo shell. Delete render_demo_home, DEMO_HOME_CSS, and the
    # demo_view branch once the walkthrough is over.
    src = mark_data_uri()
    logo = f'<img src="{src}" alt="" draggable="false" />' if src else ""
    home = _crm_icon('<path d="M4.5 11 12 4.5 19.5 11V19a1 1 0 0 1-1 1h-4.2v-5.2h-4.6V20H5.5a1 1 0 0 1-1-1v-8z"/>')
    recent = _crm_icon('<circle cx="12" cy="12" r="7"/><path d="M12 8.2V12l2.7 1.7"/>')
    saved = _crm_icon('<path d="M7 4.8h10a1 1 0 0 1 1 1V20l-6-3.1L6 20V5.8a1 1 0 0 1 1-1z"/>')
    accounts = _crm_icon('<path d="M4.5 19.5V9L10 5.8v13.7"/><path d="M10 19.5V11h9.2v8.5"/><path d="M13 14h2.4M13 16.6h2.4"/>')
    areas = _crm_icon('<rect x="4.5" y="4.5" width="6.2" height="6.2" rx="1.2"/><rect x="13.3" y="4.5" width="6.2" height="6.2" rx="1.2"/><rect x="4.5" y="13.3" width="6.2" height="6.2" rx="1.2"/><rect x="13.3" y="13.3" width="6.2" height="6.2" rx="1.2"/>')
    plants = _crm_icon('<path d="M4 19.5V12l3.6 1.8V11L12 13.2V8.8l3.4 2V19.5"/><path d="M4 19.5h16"/><path d="M17.2 8.2c.8-.9 2.2-.7 2.6.4"/>')
    contacts = _crm_icon('<circle cx="12" cy="8.2" r="2.7"/><path d="M6.2 18.8c1.1-2.6 3.1-3.8 5.8-3.8s4.7 1.2 5.8 3.8"/>')
    feedback = _crm_icon('<path d="M6 16.2 4.6 18.4V7.3A1.8 1.8 0 0 1 6.4 5.5h11.2A1.8 1.8 0 0 1 19.4 7.3v6.2a1.8 1.8 0 0 1-1.8 1.8H8.2L6 16.2z"/><path d="M8.2 9h7.2M8.2 12h4.4"/>')
    visits = _crm_icon('<path d="M12 20.5s5.5-4.8 5.5-9A5.5 5.5 0 0 0 6.5 11.5c0 4.2 5.5 9 5.5 9z"/><circle cx="12" cy="11.2" r="1.7"/>')
    tasks = _crm_icon('<rect x="5" y="5" width="14" height="14" rx="2.4"/><path d="m8.2 12.1 2.4 2.4 5-5.2"/>')
    calls = _crm_icon('<path d="M8 5.2h2.2l1.2 2.8-1.5 1a11 11 0 0 0 4.9 4.9l1-1.5 2.8 1.2V16a1.6 1.6 0 0 1-1.7 1.6A12.2 12.2 0 0 1 6.4 6.9 1.6 1.6 0 0 1 8 5.2z"/>')
    notes = _crm_icon('<path d="M7 4.5h7.2L18 8.2V19a1.2 1.2 0 0 1-1.2 1.2H7A1.2 1.2 0 0 1 5.8 19V5.7A1.2 1.2 0 0 1 7 4.5z"/><path d="M14 4.8V8.4H17.6M8.4 12.2h6.2M8.4 15.4h4.2"/>')
    diary = _crm_icon('<rect x="4.5" y="5.5" width="15" height="14" rx="2"/><path d="M8 4.2v3M16 4.2v3M4.5 9.2h15"/><path d="M8.2 13h.1M12 13h.1M15.8 13h.1M8.2 16.2h.1M12 16.2h.1"/>')
    search = _crm_icon('<circle cx="11" cy="11" r="5.2"/><path d="m15.2 15.2 3.2 3.2"/>')
    bell = _crm_icon('<path d="M6.5 16.2h11l-1.1-1.6V10a4.4 4.4 0 0 0-8.8 0v4.6L6.5 16.2z"/><path d="M10.2 16.6a1.8 1.8 0 0 0 3.6 0"/>')
    help_icon = _crm_icon('<circle cx="12" cy="12" r="7.2"/><path d="M9.6 9.5a2.4 2.4 0 1 1 3.3 2.2c-.7.4-1.1.9-1.1 1.7"/><path d="M12 16.6h.1"/>')
    layout = _crm_icon('<rect x="4.5" y="5" width="6" height="6" rx="1.2"/><rect x="13.5" y="5" width="6" height="6" rx="1.2"/><rect x="4.5" y="13" width="6" height="6" rx="1.2"/><rect x="13.5" y="13" width="6" height="6" rx="1.2"/>')
    chart = _crm_icon('<path d="M5 19V5M5 19h14"/><path d="M8.5 15.5v-4M12 15.5V8.5M15.5 15.5v-2"/>')
    reload = _crm_icon('<path d="M19 12a7 7 0 1 1-2-4.9"/><path d="M19 5.2V9h-3.8"/>')
    share = _crm_icon('<circle cx="7" cy="12" r="2"/><circle cx="17" cy="7.5" r="2"/><circle cx="17" cy="16.5" r="2"/><path d="m8.8 11.1 6.3-2.7M8.8 12.9l6.3 2.7"/>')
    caret = _crm_icon('<path d="m8 10 4 4 4-4"/>')
    stack = (
        '<svg viewBox="0 0 64 64" aria-hidden="true">'
        '<rect x="16" y="18" width="30" height="22" rx="4" fill="#F7FBF8" stroke="#0E6242" stroke-width="1.6"/>'
        '<rect x="20" y="24" width="34" height="22" rx="4" fill="#ffffff" stroke="#0E6242" stroke-width="1.7"/>'
        '<path d="M26 32h16M26 37.5h10" stroke="#7EA890" stroke-width="1.7" stroke-linecap="round"/>'
        "</svg>"
    )
    nav_top = "".join(
        [
            _crm_link(home, "Home"),
            _crm_link(recent, "Recent"),
            _crm_link(saved, "Saved"),
            '<div class="crm-kicker">Customers</div>',
            _crm_link(accounts, "Accounts", current=True),
            _crm_link(areas, "Areas"),
            _crm_link(plants, "Plants"),
            _crm_link(contacts, "Contacts"),
            _crm_link(feedback, "Feedback"),
            '<div class="crm-kicker">Activities</div>',
        ]
    )
    nav_rest = "".join(
        [
            _crm_link(visits, "Visits"),
            _crm_link(tasks, "Tasks"),
            _crm_link(calls, "Calls"),
            _crm_link(notes, "Notes"),
            _crm_link(diary, "Diary"),
        ]
    )
    st.markdown(DEMO_HOME_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="crm-home">
          <header class="crm-top">
            <div class="crm-brand">
              <div class="crm-logo">{logo}</div>
              <span class="crm-brand-name">Heidelberg Materials</span>
              <span class="crm-brand-chip">Sales desk</span>
            </div>
            <div class="crm-search">{search}<span>Search accounts or plants</span></div>
            <div class="crm-utils">
              <div class="crm-util">{bell}</div>
              <div class="crm-util">{help_icon}</div>
              <div class="crm-avatar">MO</div>
            </div>
          </header>
          <main class="crm-stage">
            <section class="crm-panel">
              <div class="crm-tools">
                <div class="crm-tools-left">
                  <span class="crm-tool">{layout}Layout</span>
                  <span class="crm-tool">{chart}Chart</span>
                  <span class="crm-tool">{reload}Reload</span>
                  <span class="crm-tool">{share}Share list</span>
                </div>
                <div class="crm-tools-right">
                  <span class="crm-tool">Columns</span>
                  <div class="crm-filter">Filter this list</div>
                </div>
              </div>
              <div class="crm-viewhead">
                <h1>Accounts on my desk {caret}</h1>
              </div>
              <div class="crm-cols">
                <span>Account {caret}</span>
                <span>Group</span>
                <span>City</span>
                <span>Plant</span>
                <span>Region</span>
              </div>
              <div class="crm-empty">
                <div class="crm-empty-mark">{stack}</div>
                <p>Nothing on this list yet</p>
                <span>Accounts you keep close will show up here.</span>
              </div>
            </section>
          </main>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="crm_nav"):
        st.markdown(nav_top, unsafe_allow_html=True)
        if st.button("Sales chat", key="crm_open_chat", type="tertiary", width="stretch"):
            st.session_state.demo_view = "chat"
            st.rerun()
        st.markdown(nav_rest, unsafe_allow_html=True)


st.set_page_config(
    layout="wide",
    page_title="Sales@RMC · Heidelberg Materials",
    page_icon=str(MARK_PATH),
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)

if "demo_view" not in st.session_state:
    st.session_state.demo_view = "home"
if st.session_state.demo_view != "chat":
    render_demo_home()
    st.stop()

render_top_bar()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "file_signature" not in st.session_state:
    st.session_state.file_signature = None
if "filename" not in st.session_state:
    st.session_state.filename = None
if "active_df" not in st.session_state:
    st.session_state.active_df = None
if "active_accounts" not in st.session_state:
    st.session_state.active_accounts = None
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "pending_display" not in st.session_state:
    st.session_state.pending_display = None
if "show_meeting_picker" not in st.session_state:
    st.session_state.show_meeting_picker = False
if "show_next_steps" not in st.session_state:
    st.session_state.show_next_steps = False
if "next_steps_meeting" not in st.session_state:
    st.session_state.next_steps_meeting = None
if "focused_account" not in st.session_state:
    st.session_state.focused_account = RECORD_FOCUS_ALL
if "last_focused_account" not in st.session_state:
    st.session_state.last_focused_account = RECORD_FOCUS_ALL
if "focus_reset_nonce" not in st.session_state:
    st.session_state.focus_reset_nonce = 0
if "chat_summary" not in st.session_state:
    st.session_state.chat_summary = None
if "chat_summary_saved" not in st.session_state:
    st.session_state.chat_summary_saved = False
if "meeting_prep_pack" not in st.session_state:
    st.session_state.meeting_prep_pack = None
if "meeting_prep_saved" not in st.session_state:
    st.session_state.meeting_prep_saved = False
if "chats" not in st.session_state:
    st.session_state.chats = []
if "next_chat_id" not in st.session_state:
    st.session_state.next_chat_id = 1
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None


def derive_chat_title(chat: dict) -> str:
    for message in chat.get("messages") or []:
        if message.get("role") == "user":
            text = str(message.get("content", "")).replace("\n", " ").strip()
            if text:
                return text[:42]
    filename = chat.get("filename")
    if filename:
        return filename
    return "New chat"


def make_chat() -> dict:
    chat_id = st.session_state.next_chat_id
    st.session_state.next_chat_id += 1
    return {
        "id": chat_id,
        "title": "New chat",
        "messages": [],
        "df": None,
        "accounts_df": None,
        "filename": None,
        "file_signature": None,
        "pending_prompt": None,
        "pending_display": None,
        "show_meeting_picker": False,
        "show_next_steps": False,
        "next_steps_meeting": None,
        "focused_account": RECORD_FOCUS_ALL,
        "last_focused_account": RECORD_FOCUS_ALL,
        "focus_reset_nonce": 0,
        "chat_summary": None,
        "chat_summary_saved": False,
        "meeting_prep_pack": None,
        "meeting_prep_saved": False,
    }


def get_chat(chat_id: int) -> dict | None:
    for chat in st.session_state.chats:
        if chat["id"] == chat_id:
            return chat
    return None


def chat_data_path(chat_id: int) -> Path:
    return STORE_DIR / f"data_{chat_id}.csv"


def accounts_data_path(chat_id: int) -> Path:
    return STORE_DIR / f"accounts_{chat_id}.csv"


def serialize_chat_for_store(chat: dict) -> dict:
    payload = {key: value for key, value in chat.items() if key not in {"df", "accounts_df"}}
    signature = payload.get("file_signature")
    if isinstance(signature, tuple):
        payload["file_signature"] = list(signature)
    return payload


def persist_store() -> None:
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        used_ids: set[int] = set()
        chats_payload = []
        for chat in st.session_state.chats:
            chat_id = chat["id"]
            used_ids.add(chat_id)
            chats_payload.append(serialize_chat_for_store(chat))
            for path, frame in (
                (chat_data_path(chat_id), chat.get("df")),
                (accounts_data_path(chat_id), chat.get("accounts_df")),
            ):
                if frame is not None:
                    frame.to_csv(path, index=False)
                elif path.exists():
                    path.unlink()
        for leftover in list(STORE_DIR.glob("data_*.csv")) + list(STORE_DIR.glob("accounts_*.csv")):
            try:
                leftover_id = int(leftover.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            if leftover_id not in used_ids:
                leftover.unlink()
        state = {
            "next_chat_id": st.session_state.next_chat_id,
            "active_chat_id": st.session_state.active_chat_id,
            "chats": chats_payload,
        }
        tmp_path = STORE_STATE_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(state, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp_path.replace(STORE_STATE_PATH)
    except Exception:
        pass


def load_store() -> dict | None:
    try:
        if not STORE_STATE_PATH.exists():
            return None
        data = json.loads(STORE_STATE_PATH.read_text(encoding="utf-8"))
        chats = []
        for payload in data.get("chats") or []:
            chat = dict(payload)
            signature = chat.get("file_signature")
            if isinstance(signature, list):
                chat["file_signature"] = tuple(signature)
            data_path = chat_data_path(chat["id"])
            if data_path.exists():
                try:
                    chat["df"] = pd.read_csv(data_path)
                except Exception:
                    chat["df"] = None
            else:
                chat["df"] = None
            accounts_path = accounts_data_path(chat["id"])
            if accounts_path.exists():
                try:
                    chat["accounts_df"] = pd.read_csv(accounts_path)
                except Exception:
                    chat["accounts_df"] = None
            else:
                chat["accounts_df"] = None
            chats.append(chat)
        next_chat_id = int(data.get("next_chat_id") or 1)
        if chats:
            next_chat_id = max(next_chat_id, max(chat["id"] for chat in chats) + 1)
        return {
            "next_chat_id": next_chat_id,
            "active_chat_id": data.get("active_chat_id"),
            "chats": chats,
        }
    except Exception:
        return None


def restore_store_if_needed() -> None:
    if st.session_state.get("store_loaded"):
        return
    st.session_state.store_loaded = True
    stored = load_store()
    if not stored or not stored["chats"]:
        return
    st.session_state.chats = stored["chats"]
    st.session_state.next_chat_id = stored["next_chat_id"]
    active_id = stored["active_chat_id"]
    overflow = len(st.session_state.chats) > MAX_CHATS
    trim_chats_to_limit()
    if get_chat(active_id):
        load_chat(active_id)
    else:
        load_chat(st.session_state.chats[0]["id"])
    if overflow:
        persist_store()


def save_active_chat() -> None:
    chat = get_chat(st.session_state.active_chat_id) if st.session_state.active_chat_id else None
    if chat is None:
        return
    chat["messages"] = list(st.session_state.messages)
    chat["df"] = st.session_state.active_df
    chat["accounts_df"] = st.session_state.active_accounts
    chat["filename"] = st.session_state.filename
    chat["file_signature"] = st.session_state.file_signature
    chat["pending_prompt"] = st.session_state.pending_prompt
    chat["pending_display"] = st.session_state.pending_display
    chat["show_meeting_picker"] = st.session_state.show_meeting_picker
    chat["show_next_steps"] = st.session_state.show_next_steps
    chat["next_steps_meeting"] = st.session_state.next_steps_meeting
    chat["focused_account"] = st.session_state.focused_account
    chat["last_focused_account"] = st.session_state.last_focused_account
    chat["focus_reset_nonce"] = st.session_state.focus_reset_nonce
    chat["chat_summary"] = st.session_state.chat_summary
    chat["chat_summary_saved"] = st.session_state.chat_summary_saved
    chat["meeting_prep_pack"] = st.session_state.meeting_prep_pack
    chat["meeting_prep_saved"] = st.session_state.meeting_prep_saved
    chat["title"] = derive_chat_title(chat)
    bring_chat_to_front(chat["id"])
    persist_store()


def load_chat(chat_id: int) -> None:
    chat = get_chat(chat_id)
    if chat is None:
        return
    st.session_state.active_chat_id = chat_id
    st.session_state.messages = list(chat["messages"])
    st.session_state.active_df = chat.get("df")
    st.session_state.active_accounts = chat.get("accounts_df")
    st.session_state.filename = chat.get("filename")
    st.session_state.file_signature = chat.get("file_signature")
    st.session_state.pending_prompt = chat.get("pending_prompt")
    st.session_state.pending_display = chat.get("pending_display")
    st.session_state.show_meeting_picker = chat.get("show_meeting_picker", False)
    st.session_state.show_next_steps = chat.get("show_next_steps", False)
    st.session_state.next_steps_meeting = chat.get("next_steps_meeting")
    st.session_state.focused_account = chat.get("focused_account", RECORD_FOCUS_ALL)
    st.session_state.last_focused_account = chat.get(
        "last_focused_account",
        st.session_state.focused_account,
    )
    st.session_state.focus_reset_nonce = chat.get("focus_reset_nonce", 0)
    st.session_state.chat_summary = chat.get("chat_summary")
    st.session_state.chat_summary_saved = chat.get("chat_summary_saved", False)
    st.session_state.meeting_prep_pack = chat.get("meeting_prep_pack")
    st.session_state.meeting_prep_saved = chat.get("meeting_prep_saved", False)


def bring_chat_to_front(chat_id: int) -> None:
    chats = st.session_state.chats
    for index, chat in enumerate(chats):
        if chat["id"] == chat_id:
            if index:
                chats.insert(0, chats.pop(index))
            return


def chat_is_blank(chat: dict) -> bool:
    return not chat.get("messages") and chat.get("df") is None


def chat_has_conversation(chat: dict) -> bool:
    return any(
        message.get("role") == "user" and str(message.get("content", "")).strip()
        for message in chat.get("messages") or []
    )


def discard_chat_record(chat_id: int) -> None:
    st.session_state.chats = [chat for chat in st.session_state.chats if chat["id"] != chat_id]
    try:
        for leftover in (chat_data_path(chat_id), accounts_data_path(chat_id)):
            if leftover.exists():
                leftover.unlink()
    except Exception:
        pass


def trim_chats_to_limit() -> None:
    while len(st.session_state.chats) > MAX_CHATS:
        discard_chat_record(st.session_state.chats[-1]["id"])


def start_new_chat() -> None:
    save_active_chat()
    current = get_chat(st.session_state.active_chat_id)
    if current is not None and chat_is_blank(current):
        return
    while len(st.session_state.chats) >= MAX_CHATS:
        discard_chat_record(st.session_state.chats[-1]["id"])
    chat = make_chat()
    st.session_state.chats.insert(0, chat)
    load_chat(chat["id"])
    persist_store()


def delete_chat(chat_id: int) -> None:
    save_active_chat()
    discard_chat_record(chat_id)
    if not st.session_state.chats:
        start_new_chat()
        return
    if st.session_state.active_chat_id == chat_id:
        load_chat(st.session_state.chats[0]["id"])
    persist_store()


def ensure_chats() -> None:
    if not st.session_state.chats:
        chat = make_chat()
        if st.session_state.messages or st.session_state.active_df is not None:
            chat["messages"] = list(st.session_state.messages)
            chat["df"] = st.session_state.active_df
            chat["accounts_df"] = st.session_state.active_accounts
            chat["filename"] = st.session_state.filename
            chat["file_signature"] = st.session_state.file_signature
            chat["pending_prompt"] = st.session_state.pending_prompt
            chat["pending_display"] = st.session_state.pending_display
            chat["show_meeting_picker"] = st.session_state.show_meeting_picker
            chat["show_next_steps"] = st.session_state.show_next_steps
            chat["next_steps_meeting"] = st.session_state.next_steps_meeting
            chat["focused_account"] = st.session_state.focused_account
            chat["last_focused_account"] = st.session_state.last_focused_account
            chat["focus_reset_nonce"] = st.session_state.focus_reset_nonce
            chat["chat_summary"] = st.session_state.chat_summary
            chat["chat_summary_saved"] = st.session_state.chat_summary_saved
            chat["meeting_prep_pack"] = st.session_state.meeting_prep_pack
            chat["meeting_prep_saved"] = st.session_state.meeting_prep_saved
            chat["title"] = derive_chat_title(chat)
        st.session_state.chats.append(chat)
        st.session_state.active_chat_id = chat["id"]
        return
    if get_chat(st.session_state.active_chat_id) is None:
        load_chat(st.session_state.chats[0]["id"])


def queue_prompt(prompt: str, display: str) -> None:
    st.session_state.pending_prompt = prompt
    st.session_state.pending_display = display
    save_active_chat()
    st.rerun()


def reset_conversation(*, new_chat: bool) -> None:
    if new_chat:
        start_new_chat()
        return
    st.session_state.messages = []
    st.session_state.pending_prompt = None
    st.session_state.pending_display = None
    st.session_state.show_meeting_picker = False
    st.session_state.show_next_steps = False
    st.session_state.next_steps_meeting = None
    st.session_state.chat_summary = None
    st.session_state.chat_summary_saved = False
    st.session_state.meeting_prep_pack = None
    st.session_state.meeting_prep_saved = False
    st.session_state.focused_account = RECORD_FOCUS_ALL
    st.session_state.last_focused_account = RECORD_FOCUS_ALL
    st.session_state.focus_reset_nonce += 1
    widget_key = f"record_focus_{st.session_state.active_chat_id}_{st.session_state.focus_reset_nonce - 1}"
    if widget_key in st.session_state:
        del st.session_state[widget_key]
    save_active_chat()


def current_session_is_active() -> bool:
    has_user = any(message.get("role") == "user" for message in st.session_state.messages)
    has_assistant = any(message.get("role") == "assistant" for message in st.session_state.messages)
    return has_user and has_assistant


def format_meeting_notes(messages: list[dict]) -> str:
    blocks: list[str] = []
    for message in messages:
        role = "User" if message["role"] == "user" else "Assistant"
        content = str(message.get("content", "")).strip()
        blocks.append(f"{role}:\n{content}")
    return "\n\n".join(blocks) if blocks else "No meeting notes yet.\n"


def strip_model_fences(raw: str) -> str:
    text = (raw or "").strip()
    if "```" not in text:
        return text
    chunks: list[str] = []
    parts = text.split("```")
    for index, part in enumerate(parts):
        if index % 2 == 0:
            continue
        if part.lower().startswith("csv"):
            part = part[3:]
        cleaned = part.strip()
        if cleaned:
            chunks.append(cleaned)
    return "\n".join(chunks) if chunks else text


def section_csv(text: str, marker: str, stop_markers: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = None
    stops = {name.lower() for name in stop_markers}
    for index, line in enumerate(lines):
        if line.lower().rstrip(":") == marker.lower():
            start = index + 1
            break
    if start is None:
        raise ValueError(f"The model did not return an {marker} table.")
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].lower().rstrip(":") in stops:
            end = index
            break
    block = "\n".join(lines[start:end]).strip()
    if not block:
        raise ValueError(f"The {marker} table was empty.")
    return block


def normalize_named_frame(df: pd.DataFrame, columns: tuple[str, ...], label: str) -> pd.DataFrame:
    canonical = {name.lower(): name for name in columns}
    renamed = {}
    for column in df.columns:
        key = str(column).strip().lower()
        if key in canonical:
            renamed[column] = canonical[key]
    frame = df.rename(columns=renamed)
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing: " + ", ".join(missing))
    frame = frame.loc[:, list(columns)].dropna(how="all")
    for column in columns:
        frame[column] = frame[column].astype(str).str.strip()
        frame.loc[frame[column].str.lower().eq("nan"), column] = ""
    key_column = columns[0]
    frame = frame[frame[key_column].ne("")]
    if frame.empty:
        raise ValueError(f"{label} had no usable rows.")
    return frame.reset_index(drop=True)


_MIX_PREFIX = re.compile(
    r"^(?:CEM(?:\s*[IVX/A-Z.-]*)?(?:\s+\d+(?:[.,]\d+)?)?|C\s*\d{1,2}\s*/\s*\d{1,2})\s*[-–:—]*\s*",
    re.IGNORECASE,
)
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")


def meeting_subject(value: str) -> str:
    cleaned = _MIX_PREFIX.sub("", value).strip(" -–:—")
    if cleaned:
        return cleaned[:1].upper() + cleaned[1:]
    return value.strip()


def _name_hits(series: pd.Series, names: set[str]) -> int:
    values = series.astype(str).str.strip().str.casefold()
    return int(values.isin(names).sum())


def _mostly_times(series: pd.Series) -> bool:
    values = [value.strip() for value in series.astype(str).tolist() if value.strip()]
    if not values:
        return False
    hits = sum(1 for value in values if _WHEN.match(value))
    return hits / len(values) >= 0.6


def align_regarding(appointments: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """Put the company name in Regarding when the model swaps it with the start time."""
    names = {
        name.casefold()
        for name in accounts["Account Name"].astype(str).str.strip()
        if name.strip()
    }
    if not names or _name_hits(appointments["Regarding"], names) >= max(1, len(appointments) // 2):
        return appointments
    best_column = max(appointments.columns, key=lambda column: _name_hits(appointments[column], names))
    if _name_hits(appointments[best_column], names) < max(1, len(appointments) // 2):
        return appointments
    if best_column == "Regarding":
        return appointments
    fixed = appointments.copy()
    if best_column == "Start" and _mostly_times(fixed["Regarding"]):
        start = fixed["Start"].copy()
        fixed["Start"] = fixed["Regarding"]
        fixed["Regarding"] = start
        return fixed
    fixed["Regarding"] = fixed[best_column]
    return fixed


def link_appointments_to_accounts(
    appointments: pd.DataFrame,
    accounts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    appointments = align_regarding(appointments, accounts)
    appointments = appointments.copy()
    appointments["Subject"] = appointments["Subject"].map(meeting_subject)
    appointments["Owner"] = APPOINTMENT_OWNER
    accounts = accounts.copy()
    accounts["Owner"] = ACCOUNT_OWNER
    canonical = {
        name.casefold(): name
        for name in accounts["Account Name"].astype(str).str.strip()
        if name.strip()
    }
    appointments["Regarding"] = appointments["Regarding"].map(
        lambda value: canonical.get(str(value).strip().casefold(), str(value).strip())
    )
    regarding = set(appointments["Regarding"])
    missing = sorted(name for name in regarding if name and name not in set(canonical.values()))
    if missing:
        raise ValueError(
            "Appointments regard accounts that are not in the Accounts table: "
            + ", ".join(missing)
        )
    linked = accounts[accounts["Account Name"].isin(regarding)].reset_index(drop=True)
    if linked.empty:
        raise ValueError("No accounts matched the appointments.")
    return appointments, linked


def _request_test_tables(api_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You create realistic CRM sample data for a ready-mix concrete salesperson. "
                    "Return only the two labeled CSV tables. No explanation and no markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create two related tables for Heidelberg Materials ready-mix concrete sales.\n"
                    "These are appointments, not opportunities or leads.\n"
                    "Output exactly this shape:\n\n"
                    "APPOINTMENTS\n"
                    "Subject,Regarding,Start,End,Location,Owner,Status,Description\n"
                    "Slab pour review,Balkan Construction,2026-11-04 09:30,2026-11-04 10:15,Marina Tower site,Momchil,Scheduled,Agree pour window and pump\n\n"
                    "ACCOUNTS\n"
                    "Account Name,Primary Contact,Phone,City,Customer Type,Plant,Owner\n"
                    "Balkan Construction,Ivan Petrov,+359 88 111 2233,Sofia,Contractor,Plant Sofia North,Bulgaria\n\n"
                    "Rules:\n"
                    "- Invent new rows. Do not copy the examples.\n"
                    "- Every appointment Owner is exactly Momchil. He is the salesperson in the meeting.\n"
                    "- Every account Owner is exactly Bulgaria. That is the country team, not a person.\n"
                    "- 8 appointments and 5 accounts.\n"
                    "- Regarding is the company the meeting is about. It must exactly equal an Account Name.\n"
                    "- Regarding is never a date or a time. Start and End are the only date columns.\n"
                    "- Every account is the Regarding value of at least one appointment.\n"
                    "- Appointments are site visits, pour reviews, mix-design meetings, or plant walkthroughs for ready-mix concrete.\n"
                    "- Subject is only the meeting name, such as Slab pour review or Plant walkthrough. Do not put a cement or strength class in front of it. Never start Subject with C25/30, C30/37, CEM I, or anything similar.\n"
                    "- Status is one of: Scheduled, Completed, Canceled.\n"
                    "- Start and End are YYYY-MM-DD HH:MM.\n"
                    "- Customer Type is one of: Contractor, Developer, Precast producer.\n"
                    "- Do not put commas inside any field.\n"
                    "- No other text before, between, or after the two tables."
                ),
            },
        ],
        temperature=0.4,
        max_tokens=2200,
    )
    raw = strip_model_fences((response.choices[0].message.content or "").strip())
    appointments = pd.read_csv(io.StringIO(section_csv(raw, "APPOINTMENTS", ("ACCOUNTS",))))
    accounts = pd.read_csv(io.StringIO(section_csv(raw, "ACCOUNTS", ("APPOINTMENTS",))))
    appointments = normalize_named_frame(appointments, APPOINTMENT_COLUMNS, "Appointments")
    accounts = normalize_named_frame(accounts, ACCOUNT_COLUMNS, "Accounts")
    return link_appointments_to_accounts(appointments, accounts)


def generate_test_tables(api_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            return _request_test_tables(api_key)
        except ValueError as exc:
            last_error = exc
    raise last_error if last_error is not None else ValueError("Could not generate test data.")


def install_generated_dataframe(appointments: pd.DataFrame, accounts: pd.DataFrame) -> None:
    st.session_state.messages = []
    st.session_state.pending_prompt = None
    st.session_state.pending_display = None
    st.session_state.show_meeting_picker = False
    st.session_state.show_next_steps = False
    st.session_state.next_steps_meeting = None
    st.session_state.chat_summary = None
    st.session_state.chat_summary_saved = False
    st.session_state.meeting_prep_pack = None
    st.session_state.meeting_prep_saved = False
    st.session_state.focused_account = RECORD_FOCUS_ALL
    st.session_state.last_focused_account = RECORD_FOCUS_ALL
    st.session_state.focus_reset_nonce += 1
    widget_key = f"record_focus_{st.session_state.active_chat_id}_{st.session_state.focus_reset_nonce - 1}"
    if widget_key in st.session_state:
        del st.session_state[widget_key]
    st.session_state.file_signature = (TEST_DATA_FILENAME, time.time_ns())
    st.session_state.filename = TEST_DATA_FILENAME
    st.session_state.active_df = appointments
    st.session_state.active_accounts = accounts
    save_active_chat()


def run_generate_test_data() -> None:
    if not is_valid_api_key(API_KEY):
        st.error("Add DEEPSEEK_API_KEY to your .env file, then restart the app.")
        return
    try:
        with st.spinner("Generating appointments and accounts..."):
            appointments, accounts = generate_test_tables(API_KEY)
        install_generated_dataframe(appointments, accounts)
    except Exception as exc:
        st.error(f"Could not generate test data: {exc}")
        return
    st.rerun()


restore_store_if_needed()
ensure_chats()

with st.sidebar:
    if st.button(
        "New chat",
        key="new_chat",
        icon=":material/add:",
        type="primary",
        width="stretch",
    ):
        start_new_chat()
        st.rerun()
    if st.button(
        "Generate test data",
        key="generate_test_data_side",
        icon=":material/dataset:",
        width="stretch",
        disabled=not is_valid_api_key(API_KEY),
    ):
        run_generate_test_data()
    visible_chats = [chat for chat in st.session_state.chats if chat_has_conversation(chat)]
    if visible_chats:
        st.markdown('<p class="hm-nav-label">Chats</p>', unsafe_allow_html=True)
    for chat in visible_chats:
        open_col, delete_col = st.columns([0.86, 0.14], gap="xxsmall")
        is_active = chat["id"] == st.session_state.active_chat_id
        with open_col:
            if st.button(
                chat["title"],
                key=f"open_chat_{chat['id']}",
                width="stretch",
                type="primary" if is_active else "tertiary",
            ):
                if not is_active:
                    save_active_chat()
                    load_chat(chat["id"])
                    bring_chat_to_front(chat["id"])
                    persist_store()
                    st.rerun()
        with delete_col:
            if st.button(
                "",
                key=f"del_chat_{chat['id']}",
                icon=":material/close:",
                help="Delete chat",
                type="tertiary",
            ):
                delete_chat(chat["id"])
                st.rerun()

df = st.session_state.active_df

def mark_chat_summary_saved() -> None:
    st.session_state.chat_summary_saved = True


def mark_meeting_prep_saved() -> None:
    st.session_state.meeting_prep_saved = True


render_workspace_header(
    df,
    focused_dataframe(df, st.session_state.focused_account) if df is not None else None,
)

if not is_valid_api_key(API_KEY):
    st.warning("Add DEEPSEEK_API_KEY to your .env file, then restart the app.")

focus_column = None
if df is not None:
    with st.container(key="data_tools"):
        record_options = record_focus_options(df)
        current_focus = st.session_state.focused_account
        if current_focus not in record_options:
            current_focus = RECORD_FOCUS_ALL
            st.session_state.focused_account = RECORD_FOCUS_ALL
        focus_column = find_focus_column(df)
        if "show_crm_tables" not in st.session_state:
            st.session_state.show_crm_tables = True
        tables_open = st.session_state.show_crm_tables
        label_col, toggle_col = st.columns([4, 1], vertical_alignment="center")
        with label_col:
            st.markdown("**Appointments and accounts**")
        with toggle_col:
            if st.button(
                "Hide" if tables_open else "Show",
                key="toggle_crm_tables",
                type="tertiary",
                icon=":material/visibility_off:" if tables_open else ":material/visibility:",
            ):
                st.session_state.show_crm_tables = not tables_open
                st.rerun()
        if tables_open:
            st.caption("Regarding on an appointment is the Account Name.")
            st.markdown("**Appointments**")
            st.dataframe(df, width="stretch", hide_index=True, height=240)
            accounts = st.session_state.get("active_accounts")
            if accounts is not None and not getattr(accounts, "empty", True):
                st.markdown("**Accounts**")
                st.dataframe(accounts, width="stretch", hide_index=True, height=220)

ai_df = focused_dataframe(df, st.session_state.focused_account) if df is not None else None
ready = df is not None and is_valid_api_key(API_KEY)

focusing_specific_record = st.session_state.focused_account not in {
    RECORD_FOCUS_ALL,
    "All Accounts",
}


for message in st.session_state.messages:
    avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

prompt = st.session_state.pending_prompt
display = st.session_state.pending_display
if prompt:
    st.session_state.pending_prompt = None
    st.session_state.pending_display = None

if (df is not None and focus_column is not None) or current_session_is_active():
    with st.container(key="command_bar", horizontal=True, vertical_alignment="center", gap="small"):
        if df is not None and focus_column is not None:
            if "show_focus_picker" not in st.session_state:
                st.session_state.show_focus_picker = False
            focused_name = st.session_state.focused_account
            focus_label = (
                "Focus record"
                if focused_name in {RECORD_FOCUS_ALL, "All Accounts"}
                else focused_name
            )
            if st.button(
                focus_label,
                key="focus_record_btn",
                icon=":material/filter_list:",
                type="tertiary",
            ):
                st.session_state.show_focus_picker = not st.session_state.show_focus_picker
                st.rerun()
            if st.session_state.show_focus_picker:
                picked = st.selectbox(
                    "Focus record",
                    options=record_options,
                    index=record_options.index(focused_name)
                    if focused_name in record_options
                    else 0,
                    key=f"record_focus_{st.session_state.active_chat_id}_{st.session_state.focus_reset_nonce}",
                    label_visibility="collapsed",
                    help="Lists appointment subjects. Regarding is the account for that meeting.",
                )
                if picked != focused_name:
                    st.session_state.focused_account = picked
                    st.session_state.last_focused_account = picked
                    st.session_state.show_focus_picker = False
                    if ready and picked not in {RECORD_FOCUS_ALL, "All Accounts"}:
                        st.session_state.show_next_steps = True
                        st.session_state.next_steps_meeting = picked
                        queue_prompt(
                            record_summary_prompt(picked),
                            f"Summary: {picked}",
                        )
                    st.rerun()
        if current_session_is_active() and df is not None:
            if focusing_specific_record:
                if st.button(
                    "Next steps",
                    key="next_steps_record",
                    icon=":material/checklist:",
                    type="tertiary",
                    disabled=not ready,
                ):
                    record = st.session_state.focused_account
                    queue_prompt(next_steps_prompt(record), f"Next steps — {record}")
            else:
                if st.button(
                    "Summary for all records",
                    icon=":material/summarize:",
                    type="tertiary",
                    disabled=not ready,
                ):
                    st.session_state.show_next_steps = True
                    st.session_state.next_steps_meeting = None
                    queue_prompt(SUMMARY_PROMPT, "Summary for all records")
                if st.session_state.show_next_steps:
                    if st.button(
                        "Next steps",
                        key="next_steps_all",
                        icon=":material/checklist:",
                        type="tertiary",
                        disabled=not ready,
                    ):
                        queue_prompt(next_steps_prompt(), "Next steps")
            if st.session_state.get("chat_summary_saved") and st.session_state.chat_summary:
                st.button(
                    "Chat summary saved",
                    disabled=True,
                    icon=":material/check:",
                    type="tertiary",
                    key="chat_summary_saved_btn",
                )
            elif st.session_state.chat_summary:
                st.download_button(
                    "Download chat summary",
                    data=st.session_state.chat_summary,
                    file_name="Chat_Summary.txt",
                    mime="text/plain",
                    icon=":material/download:",
                    type="tertiary",
                    on_click=mark_chat_summary_saved,
                )
            elif st.button(
                "Download chat summary",
                icon=":material/download:",
                type="tertiary",
                key="chat_summary_generate",
            ):
                if not is_valid_api_key(API_KEY):
                    st.error("Add DEEPSEEK_API_KEY to your .env file, then restart the app.")
                else:
                    try:
                        st.session_state.chat_summary = generate_chat_summary(
                            API_KEY,
                            st.session_state.messages,
                        )
                        save_active_chat()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not summarize the chat: {exc}")
            if st.session_state.get("meeting_prep_saved") and st.session_state.meeting_prep_pack:
                st.button(
                    "Meeting prep saved",
                    disabled=True,
                    icon=":material/check:",
                    type="tertiary",
                    key="meeting_prep_saved_btn",
                )
            elif st.session_state.meeting_prep_pack:
                st.download_button(
                    "Download meeting prep",
                    data=st.session_state.meeting_prep_pack,
                    file_name="Meeting_Prep_Pack.txt",
                    mime="text/plain",
                    icon=":material/event_note:",
                    type="tertiary",
                    on_click=mark_meeting_prep_saved,
                    key="meeting_prep_download",
                )
            elif st.button(
                "Download meeting prep",
                icon=":material/event_note:",
                type="tertiary",
                key="meeting_prep_generate",
            ):
                if not is_valid_api_key(API_KEY):
                    st.error("Add DEEPSEEK_API_KEY to your .env file, then restart the app.")
                else:
                    try:
                        prep_df = ai_df if ai_df is not None else df
                        st.session_state.meeting_prep_pack = generate_meeting_prep_pack(
                            API_KEY,
                            st.session_state.messages,
                            prep_df,
                        )
                        save_active_chat()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not create the meeting prep pack: {exc}")
        if current_session_is_active() and st.button(
            "Clear chat",
            key="clear_chat",
            icon=":material/delete:",
            type="tertiary",
        ):
            reset_conversation(new_chat=False)
            st.rerun()

chat_prompt = st.chat_input("Ask about pours, plants, or the next call", disabled=not ready)
if chat_prompt:
    prompt = chat_prompt
    display = None

if prompt and ready:
    run_chat_turn(prompt, ai_df if ai_df is not None else df, API_KEY, display=display)
    save_active_chat()
    st.rerun()

save_active_chat()
