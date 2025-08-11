# streamlit_app.py
import re
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

def _get_email_col(ws):
    headers = ws.row_values(1)
    try:
        return headers.index("email") + 1  # 1-based
    except ValueError:
        return None

def email_already_voted(email: str) -> bool:
    if not email:
        return False
    ws = _get_ws()
    col = _get_email_col(ws)
    if not col:
        return False
    existing = [e.strip().lower() for e in ws.col_values(col)[1:]]  # skip header
    return email.strip().lower() in set(existing)

def delete_votes_for_email(email: str):
    """Delete any existing rows for this email (safe for small sheets)."""
    if not email:
        return
    ws = _get_ws()
    col = _get_email_col(ws)
    if not col:
        return
    # Only delete matches in the email column
    cells = [c for c in ws.findall(email) if c.col == col]
    rows = sorted({c.row for c in cells if c.row != 1}, reverse=True)
    for r in rows:
        ws.delete_rows(r)

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
### In a quadratic voting system, each participant gets credits they can spend on votes.
### **The stronger your support, the more credits it costs.**

This system can be more effective at finding a **collective consensus** while still letting each voter emphasize their choices.

Here, each participant gets **9 credits**:

- **1 vote** for an option costs **1² = 1** credit  
- **2 votes** for the same option cost **2² = 4** credits  
- **3 votes** for the same option cost **3² = 9** credits

**How to vote here**
1. Pick **one box per row** (or leave a row blank).  
2. Spend **up to 9 credits** total — the counter shows what you’ve used and what’s left.  
3. You **can** submit with unused credits, but spending all 9 is encouraged.  
4. Don’t see a name you like? Use **Propose a different name** below, then vote on it.
""")

# ---- Email required + duplicate handling ----
st.subheader("Who’s voting?")
email = st.text_input("Email address (required to submit)", key="voter_email").strip().lower()
valid_email = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
already = email_already_voted(email) if valid_email else False

allow_replace = False
if valid_email and already:
    st.info("We already have a vote from this email. You can replace it below.")
    allow_replace = st.checkbox("Replace my previous vote with this new ballot", value=False)
    
# ---- TOP METRICS PLACEHOLDERS ----
top_m1, top_m2 = st.columns(2)

# ---- helper: keep the three boxes in a row mutually exclusive (instant) ----
def exclusify(active_key: str, row_keys: list[str]):
    if st.session_state.get(active_key, False):
        for k in row_keys:
            if k != active_key:
                st.session_state[k] = False

# Read any previously-entered "Other" name (input will be BELOW the table)
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

# --- quadratic cost + metrics (TOP)
total_cost = sum(v*v for v in votes_dict.values()) + other_vote*other_vote
remaining = BUDGET - total_cost
top_m1.metric("Total credits used", total_cost)
top_m2.metric("Credits remaining", remaining)

# ---- Propose a different name (BELOW table, before bottom metrics) ----
st.subheader("Propose a different name (optional)")
st.text_input(
    "Don't see a name you'd like to add? Put it here:",
    key="proposed_name",
    help="Type a name and it will appear as a new row above. Then you can vote on it.",
)

# --- messages
if total_cost > BUDGET:
    st.error("Over budget — uncheck something until you’re at 9 credits or less.")
elif remaining > 0:
    st.warning(
        f"You have {remaining} credit{'s' if remaining != 1 else ''} left. "
        "While you don't have to spend all your credits, it is encouraged."
    )
if email and not valid_email:
    st.error("Please enter a valid email address (e.g., name@example.com).")

# bottom metrics (duplicate, after the 'Propose' + Email sections)
bottom_m1, bottom_m2 = st.columns(2)
bottom_m1.metric("Total credits used", total_cost)
bottom_m2.metric("Credits remaining", remaining)

# allow submit as long as not over budget AND email is valid AND either not duplicate or replacing
disable_submit = (total_cost > BUDGET) or (not valid_email) or (already and not allow_replace)

# --- submit -> Google Sheets ONLY
if st.button("Submit", disabled=disable_submit, type="primary"):
    if already and allow_replace:
        delete_votes_for_email(email)

    row_out = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "email": email,
        "total_cost": total_cost,
        **votes_dict,
        "Other (text)": proposed_name if include_other else "",
        "Other (votes)": other_vote,
    }
    save_vote_to_gsheet(row_out)
    st.success("Thanks! Your vote was recorded in Google Sheets.")
    st.balloons()