# streamlit_app.py
# ------------------------------------------------------------
# Quadratic Voting app
# - Saves ballots to Google Sheets
# - Requires an email and lets a voter replace their prior vote
# - Radio-like checkbox grid (1 / 2 / 3 votes per row, max 1 checked)
# - "Propose a different name" appears below the grid
# - Metrics (Total credits used / Credits remaining) centered and styled
# - Optimized: cached Google Sheets client & cached email set; only checks
#   duplicates when the email changes
# ------------------------------------------------------------

import re
import streamlit as st
from datetime import datetime

# ===================== Google Sheets helpers (CACHED) =====================

@st.cache_resource
def _get_ws_cached():
    """
    Build and cache the Google Sheets worksheet handle for this session.

    Why cache? Streamlit re-runs the script on every UI interaction; caching
    prevents re-auth + re-open on each rerun, which keeps the UI snappy.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    # Scopes: spreadsheet access + Drive is handy for Shared Drives
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # st.secrets must include:
    #   - "gcp_service_account" (service account JSON as a dict)
    #   - "sheet_id"            (target spreadsheet ID)
    #   - "worksheet_name"      (optional; defaults to "Responses")
    secrets = st.secrets
    creds = Credentials.from_service_account_info(secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(secrets["sheet_id"])
    ws_name = secrets.get("worksheet_name", "Responses")

    # Get worksheet; create it if missing
    try:
        ws = sh.worksheet(ws_name)
    except Exception:  # gspread.exceptions.WorksheetNotFound
        ws = sh.add_worksheet(title=ws_name, rows=1000, cols=100)
    return ws


@st.cache_data(ttl=120)  # refresh email list at most every 120 seconds
def _get_email_set():
    """
    Return a set of all emails (lowercased) currently stored in the sheet.

    Cached for 120s to avoid hitting the API on every rerun. We *manually*
    clear this cache after a successful submit so new emails are visible
    immediately.
    """
    ws = _get_ws_cached()
    headers = ws.row_values(1)
    try:
        col_idx = headers.index("email") + 1  # 1-based column index
    except ValueError:
        return set()
    # Skip header row; normalize spacing and case
    return {e.strip().lower() for e in ws.col_values(col_idx)[1:]}


def email_already_voted(email: str) -> bool:
    """Fast duplicate check against the cached set."""
    if not email:
        return False
    return email.strip().lower() in _get_email_set()


def delete_votes_for_email(email: str):
    """
    Delete any existing rows for this email.
    OK for small/medium sheets. If you scale up a lot, store an index.
    """
    if not email:
        return
    ws = _get_ws_cached()
    headers = ws.row_values(1)
    try:
        col_idx = headers.index("email") + 1
    except ValueError:
        return
    # Only consider matches in the email column
    cells = [c for c in ws.findall(email) if c.col == col_idx]
    rows = sorted({c.row for c in cells if c.row != 1}, reverse=True)
    for r in rows:
        ws.delete_rows(r)


def save_vote_to_gsheet(row_dict: dict):
    """
    Append a ballot row to the sheet. If there's no header yet, write one
    using the keys of row_dict (stable column order).
    """
    ws = _get_ws_cached()
    headers = ws.row_values(1)
    if not headers:
        ws.append_row(list(row_dict.keys()))
        headers = ws.row_values(1)
    ws.append_row([row_dict.get(h, "") for h in headers])


# ============================ App config & styles ============================

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

# ---------- Metric styling ----------
# We render our *own* label above each metric and let st.metric show only the number.
# The CSS below:
#   1) Centers metric content
#   2) Hides Streamlit's internal label & delta space so the number sits right under our label
#   3) Lets you tune sizes/spacing in ONE place
st.markdown("""
<style>
/* Center the metric contents */
div[data-testid="stMetric"] { text-align: center; }
div[data-testid="stMetric"] > div {
  display: flex;
  flex-direction: column;
  align-items: center;    /* center under our custom label */
  gap: 0 !important;      /* remove internal spacing */
  margin: 0 !important;
  padding: 0 !important;
}

/* Hide Streamlit's built-in label and delta so no extra space/offset remains */
div[data-testid="stMetricLabel"] {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}
div[data-testid="stMetricDelta"] { display: none !important; }

/* OUR custom label above the number */
.metric-label{
  text-align: center;
  font-size: 1.45rem;    /* ← label size */
  font-weight: 300;      /* ← 700=bold, 800=extra bold */
  line-height: 1.0;     /* ← label line height */
  margin: 0px 0 0px;     /* ← vertical spacing around label */
}

/* The metric NUMBER */
div[data-testid="stMetricValue"]{
  font-size: 1.8rem;     /* ← number size */
  font-weight: 600;      /* ← number weight */
  line-height: 1.0;      /* ← tighter vertical spacing */
  margin: 0 !important;  /* ← remove extra margin */
  text-align: center;
}
</style>
""", unsafe_allow_html=True)

def render_metric_pair(total_cost: int, remaining: int):
    """
    Draw the two metrics centered on the page with custom labels above each number.
    Edit the column ratios below if you want a wider or narrower center block.
    """
    left, center_col, right = st.columns([1, 2, 1])  # ← widen/narrow the middle block here
    with center_col:
        c1, c2 = st.columns([1, 1])                  # ← adjust each metric's width here
        with c1:
            st.markdown('<div class="metric-label">Total credits used</div>', unsafe_allow_html=True)
            st.metric(label="", value=total_cost)     # label="" so our custom label is the only one
        with c2:
            st.markdown('<div class="metric-label">Credits remaining</div>', unsafe_allow_html=True)
            st.metric(label="", value=remaining)


# ============================== Header & help ==============================

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


# ============================== Email (first) ==============================

st.subheader("Who’s voting?")
email = st.text_input("Email address (required to submit)", key="voter_email").strip().lower()
valid_email = bool(re.match(r"^[^@\s]+@[^@\s]+\\.[^@\\s]+$", email))

# Only check duplicates when the email changes (avoids API calls on every rerun)
already = False
if valid_email:
    if email != st.session_state.get("last_checked_email"):
        st.session_state["last_checked_email"] = email
        st.session_state["email_exists"] = email_already_voted(email)
    already = st.session_state.get("email_exists", False)

allow_replace = False
if valid_email and already:
    st.info("We already have a vote from this email. You can replace it below.")
    allow_replace = st.checkbox("Replace my previous vote with this new ballot", value=False)
if email and not valid_email:
    st.error("Please enter a valid email address (e.g., name@example.com).")

# Reserve a visual spot for the TOP metrics; we'll fill it after computing totals.
top_metrics_placeholder = st.container()


# ================= Voting grid (radio-like checkboxes per row) ================

def exclusify(active_key: str, row_keys: list[str]):
    """
    Make the three checkboxes per row behave like radio buttons:
    when one is checked, uncheck the others in that row.
    """
    if st.session_state.get(active_key, False):
        for k in row_keys:
            if k != active_key:
                st.session_state[k] = False

# Read proposed name (the input lives below the table; we read it now so
# the new row appears above as soon as text is present)
proposed_name = (st.session_state.get("proposed_name") or "").strip()
include_other = bool(proposed_name)

# Header row for the grid
h0, h1, h2, h3 = st.columns([3, 1, 1, 1])
h0.markdown("**Name options**")
h1.markdown("**1 vote**")
h2.markdown("**2 votes**")
h3.markdown("**3 votes**")

votes_dict = {}
rows = OPTIONS + ([proposed_name] if include_other else [])
other_vote = 0

for i, label in enumerate(rows):
    c0, c1, c2, c3 = st.columns([3, 1, 1, 1])
    c0.write(label if label else "Other")

    # Stable keys per row so Streamlit remembers selections across reruns
    k1 = f"row{i}_v1"
    k2 = f"row{i}_v2"
    k3 = f"row{i}_v3"
    row_keys = [k1, k2, k3]

    # Disable the 'Other' row until text is entered; also clear any stale checks
    disabled = (i == len(OPTIONS) and not include_other)
    if disabled:
        for k in row_keys:
            st.session_state[k] = False

    # Three checkboxes with instant exclusivity within the row
    c1.checkbox("", key=k1, on_change=exclusify, args=(k1, row_keys), disabled=disabled)
    c2.checkbox("", key=k2, on_change=exclusify, args=(k2, row_keys), disabled=disabled)
    c3.checkbox("", key=k3, on_change=exclusify, args=(k3, row_keys), disabled=disabled)

    # Convert checkbox state → vote count (0/1/2/3)
    v = 3 if st.session_state.get(k3) else 2 if st.session_state.get(k2) else 1 if st.session_state.get(k1) else 0

    if i < len(OPTIONS):
        votes_dict[label] = v
    else:
        other_vote = v  # votes for the "Other" row

# -------- Compute totals and render TOP metrics in the placeholder --------
total_cost = sum(v * v for v in votes_dict.values()) + other_vote * other_vote
remaining = BUDGET - total_cost

with top_metrics_placeholder:
    render_metric_pair(total_cost, remaining)


# ================= Propose a different name (below the grid) =================

st.subheader("Propose a different name (optional)")
st.text_input(
    "Don't see a name you'd like to add? Put it here:",
    key="proposed_name",
    help="Type a name and it will appear as a new row above. Then you can vote on it.",
)

# Duplicate the metrics at the bottom, centered
render_metric_pair(total_cost, remaining)

# Helpful guidance about budget usage
if total_cost > BUDGET:
    st.error("Over budget — uncheck something until you’re at 9 credits or less.")
elif remaining > 0:
    st.warning(
        f"You have {remaining} credit{'s' if remaining != 1 else ''} left. "
        "While you don't have to spend all your credits, it is encouraged."
    )


# ========================= Submit gating & save =========================

# Disable submit if: over budget, invalid email, or duplicate without replace
disable_submit = (total_cost > BUDGET) or (not valid_email) or (already and not allow_replace)

if st.button("Submit", disabled=disable_submit, type="primary"):
    # If replacing prior ballot, remove old rows for this email first
    if already and allow_replace:
        delete_votes_for_email(email)

    # Append a single row representing the full ballot
    row_out = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "email": email,
        "total_cost": total_cost,
        **votes_dict,
        "Other (text)": proposed_name if include_other else "",
        "Other (votes)": other_vote,
    }
    save_vote_to_gsheet(row_out)

    # Clear the cached email set so duplicate checks reflect this submission immediately
    _get_email_set.clear()

    st.success("Thanks! Your vote was recorded in Google Sheets.")
    st.balloons()