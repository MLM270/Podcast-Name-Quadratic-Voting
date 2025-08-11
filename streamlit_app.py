# streamlit_app.py
import streamlit as st
import pandas as pd
from datetime import datetime

# ---------- Google Sheets helpers ----------
def _get_ws():
    import gspread
    from google.oauth2.service_account import Credentials

    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    secrets = st.secrets  # expects: sheet_id, worksheet_name, [gcp_service_account]
    creds = Credentials.from_service_account_info(secrets["gcp_service_account"], scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(secrets["sheet_id"])
    ws = sh.worksheet(secrets.get("worksheet_name", "Responses"))
    return ws

def save_vote_to_gsheet(row_dict: dict):
    ws = _get_ws()
    # Ensure header row exists (create once in a stable column order)
    headers = ws.row_values(1)
    if not headers:
        ws.append_row(list(row_dict.keys()))
        headers = ws.row_values(1)
    # Append values in header order so columns stay aligned even if code changes
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
The goal is to find a **collective consensus** while letting each of us *emphasize our choices*.

Check **one** box per row (or leave a row blank). You can submit with **up to 9** credits.
""")

# ---- TOP METRICS PLACEHOLDERS (we'll fill after computing totals) ----
top_m1, top_m2 = st.columns(2)

# --- read any previously-entered "Other" name from session state
proposed_name = st.session_state.get("proposed_name", "").strip()
include_other = bool(proposed_name)

# --- build the editable table (grid)
index = OPTIONS + ([proposed_name] if include_other else [])
df = pd.DataFrame(
    {"1 vote": [False]*len(index), "2 votes": [False]*len(index), "3 votes": [False]*len(index)},
    index=index,
)
df.index.name = "Name options"

edited = st.data_editor(
    df,
    num_rows="fixed",
    use_container_width=True,
    hide_index=False,
    column_config={
        "1 vote": st.column_config.CheckboxColumn(help="Costs 1 credit"),
        "2 votes": st.column_config.CheckboxColumn(help="Costs 4 credits"),
        "3 votes": st.column_config.CheckboxColumn(help="Costs 9 credits"),
    },
)

# --- "Other" input BELOW the table; adds a row on rerun if non-empty
st.subheader("Propose a different name (optional)")
st.text_input(
    "Don't see a name you'd like to add, put it here:",
    key="proposed_name",
    help="Type a name and it will appear as a new row in the table above.",
)

# --- validate: only one checkbox per row
row_counts = edited[["1 vote", "2 votes", "3 votes"]].sum(axis=1)
invalid_rows = row_counts[row_counts > 1].index.tolist()

# --- convert selections to 0/1/2/3 votes
def row_to_votes(row):
    if row["1 vote"]: return 1
    if row["2 votes"]: return 2
    if row["3 votes"]: return 3
    return 0

votes_series = edited.apply(row_to_votes, axis=1)

# split into predefined + optional Other
votes_dict = {opt: int(votes_series.get(opt, 0)) for opt in OPTIONS}
v_other = int(votes_series.get(proposed_name, 0)) if include_other else 0

# --- quadratic cost + metrics
total_cost = sum(v*v for v in votes_dict.values()) + v_other*v_other
remaining = BUDGET - total_cost

# populate the TOP metrics
top_m1.metric("Total cost used", total_cost)
top_m2.metric("Credits remaining", remaining)

# also show BOTTOM metrics (duplicate)
bottom_m1, bottom_m2 = st.columns(2)
bottom_m1.metric("Total cost used", total_cost)
bottom_m2.metric("Credits remaining", remaining)

# --- messages
if invalid_rows:
    st.error("Pick **only one** box per row.\n\nProblem rows: " + ", ".join(map(str, invalid_rows)))
if total_cost > BUDGET:
    st.error("Over budget — uncheck something until you’re at 9 credits or less.")
elif remaining > 0:
    st.warning(
        f"You have {remaining} credit{'s' if remaining != 1 else ''} left. "
        "While you don't have to spend all your credits, it is encouraged."
    )

# allow submit as long as rows are valid and not over budget
disable_submit = bool(invalid_rows) or (total_cost > BUDGET)

# --- submit -> Google Sheets ONLY
if st.button("Submit", disabled=disable_submit, type="primary"):
    row_out = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "total_cost": total_cost,
        **votes_dict,
        "Other (text)": proposed_name if include_other else "",
        "Other (votes)": v_other,
    }
    save_vote_to_gsheet(row_out)
    st.success("Thanks! Your vote was recorded in Google Sheets.")
    st.balloons()