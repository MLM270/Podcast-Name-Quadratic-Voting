# streamlit_app.py
import streamlit as st
import pandas as pd
from datetime import datetime

# ---------- Google Sheets helpers ----------
def _get_ws():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",  # helpful for Shared Drives
    ]
    secrets = st.secrets  # expects: sheet_id, worksheet_name, [gcp_service_account]
    creds = Credentials.from_service_account_info(secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(secrets["sheet_id"])
    ws = sh.worksheet(secrets.get("worksheet_name", "Responses"))
    return ws

def save_vote_to_gsheet(row_dict: dict):
    ws = _get_ws()
    headers = ws.row_values(1)
    if not headers:
        ws.append_row(list(row_dict.keys()))
        headers = ws.row_values(1)
    ws.append_row([row_dict.get(h, "") for h in headers])

# ---------- App ----------
BUDGET = 9
OPTIONS = [
    "How Did We Get Here?",
    "How In The World?",
    "I Made This For You",
    "If You Make It, They Will Come",
    "Made Possible By",
    "Make It Possible",
    "Rise and Hypothesize",
    "Rise and Realize",
    "Rise and Scrutinize",
    "Rise and Theorize",
    "What In The World?",
    "Your Passions Made Possible By",
]

st.set_page_config(page_title="Podcast Name Voting — Quadratic Voting", page_icon="📊")

st.title("Podcast Name Voting — Quadratic Voting")
st.markdown("""
In this voting system, each participant gets **9 credits** to spend however they choose.

- Casting **1 vote** for an option costs 1² = 1 credit.
- Casting **2 votes** for the same option costs 2² = 4 credits.
- Casting **3 votes** for the same option costs 3² = 9 credits.

This means the more strongly you support an option, the more it costs to express that intensity. 
The goal is to find a **collective consensus** while letting each of us emphasize our choices.
""")

# ---- TOP METRICS PLACEHOLDERS ----
top_m1, top_m2 = st.columns(2)

# ---- helper: keep the three boxes in a row mutually exclusive (instant) ----
def exclusify(active_key: str, row_keys: list[str]):
    if st.session_state.get(active_key, False):
        for k in row_keys:
            if k != active_key:
                st.session_state[k] = False

# --- "Other" input BELOW the table; adds a row on rerun if non-empty
st.subheader("Propose a different name (optional)")
st.text_input(
    "Don't see a name you'd like to add, put it here:",
    key="proposed_name",
    help="Type a name and it will appear as a new row in the table above.",
)
proposed_name = (st.session_state.get("proposed_name") or "").strip()
include_other = bool(proposed_name)

# ---- header row for the grid ----
h0, h1, h2, h3 = st.columns([3, 1, 1, 1])
h0.markdown("**Name options**")
h1.markdown("**1 vote**")
h2.markdown("**2 votes**")
h3.markdown("**3 votes**")

# ---- draw grid rows with exclusive checkboxes ----
votes_dict = {}
rows = OPTIONS + ([proposed_name] if include_other else [])
other_vote = 0

for i, label in enumerate(rows):
    c0, c1, c2, c3 = st.columns([3, 1, 1, 1])
    c0.write(label if label else "Other")

    # stable keys per row, unrelated to label text
    k1 = f"row{i}_v1"
    k2 = f"row{i}_v2"
    k3 = f"row{i}_v3"
    row_keys = [k1, k2, k3]

    # If this is the "Other" row but no text entered yet, disable & clear
    disabled = (i == len(OPTIONS) and not include_other)
    if disabled:
        for k in row_keys:
            st.session_state[k] = False

    c1.checkbox("", key=k1, on_change=exclusify, args=(k1, row_keys), disabled=disabled)
    c2.checkbox("", key=k2, on_change=exclusify, args=(k2, row_keys), disabled=disabled)
    c3.checkbox("", key=k3, on_change=exclusify, args=(k3, row_keys), disabled=disabled)

    # translate to 0/1/2/3 votes instantly
    v = 3 if st.session_state.get(k3) else 2 if st.session_state.get(k2) else 1 if st.session_state.get(k1) else 0

    if i < len(OPTIONS):
        votes_dict[label] = v
    else:
        other_vote = v  # the "Other" row

# --- quadratic cost + metrics
total_cost = sum(v*v for v in votes_dict.values()) + other_vote*other_vote
remaining = BUDGET - total_cost

top_m1.metric("Total cost used", total_cost)
top_m2.metric("Credits remaining", remaining)

# bottom metrics (duplicate)
bottom_m1, bottom_m2 = st.columns(2)
bottom_m1.metric("Total cost used", total_cost)
bottom_m2.metric("Credits remaining", remaining)

# --- messages
if total_cost > BUDGET:
    st.error("Over budget — uncheck something until you’re at 9 credits or less.")
elif remaining > 0:
    st.warning(
        f"You have {remaining} credit{'s' if remaining != 1 else ''} left. "
        "While you don't have to spend all your credits, it is encouraged."
    )

# allow submit as long as not over budget
disable_submit = (total_cost > BUDGET)

# --- submit -> Google Sheets ONLY
if st.button("Submit", disabled=disable_submit, type="primary"):
    row_out = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "total_cost": total_cost,
        **votes_dict,
        "Other (text)": proposed_name if include_other else "",
        "Other (votes)": other_vote,
    }
    save_vote_to_gsheet(row_out)
    st.success("Thanks! Your vote was recorded in Google Sheets.")
    st.balloons()