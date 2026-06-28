"""
User feedback service.

Captures two kinds of feedback from the club site:

  * General          - public; shown to everyone on the /feedback page.
  * Feature Request  - admin-only; shown (with status controls) only to admins.

Metadata lives in data/Feedback.xlsx and is mirrored to R2 via the shared
load_excel/save_excel helpers (durable storage with a local cache). When R2 is
unconfigured or unreachable, the local file is used and writes simply stay local
(save_excel's R2 upload is a best-effort retry/no-op), so submitting feedback
never errors out just because the remote store is down.

Submitters identify themselves by selecting their name from the club's player
list ("Submitted By"), so feedback is easy to consolidate per member. Anyone not
on the list picks "Non-Member" and supplies an email address instead.

Sheet schema (kept human-readable for the Excel file):
    ID | Timestamp | Submitted By | User Email | Feedback Type | Message | Status
"""
import uuid
from datetime import datetime, timezone

import pandas as pd

from services.excel_service import load_excel, save_excel

FEEDBACK_FILE = "Feedback.xlsx"

_COLUMNS = [
    "ID", "Timestamp", "Submitted By", "User Email",
    "Feedback Type", "Message", "Status",
]

FEEDBACK_TYPES = ("General", "Feature Request")
STATUSES = ("New", "In Progress", "Completed")
NON_MEMBER = "Non-Member"

_MAX_MESSAGE_LEN = 2000
_MAX_EMAIL_LEN = 200
_MAX_NAME_LEN = 120


def _load() -> pd.DataFrame:
    df = load_excel(FEEDBACK_FILE)
    if df.empty:
        return pd.DataFrame(columns=_COLUMNS)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[_COLUMNS].fillna("")


def _sanitize(text: str, max_len: int) -> str:
    """Trim whitespace, drop control characters, and cap length. XSS-safe display
    is handled by Jinja autoescaping, so we store cleaned plain text rather than
    pre-escaped markup (which would double-escape on render)."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    return cleaned.strip()[:max_len]


def submit_feedback(
    feedback_type: str, message: str, submitted_by: str, email: str = ""
) -> dict | None:
    """Validate and persist one feedback entry. Returns the stored row dict, or
    None for an invalid submission (empty message, no submitter selected, or a
    Non-Member without an email)."""
    feedback_type = (feedback_type or "").strip()
    if feedback_type not in FEEDBACK_TYPES:
        feedback_type = "General"

    message = _sanitize(message, _MAX_MESSAGE_LEN)
    if not message:
        return None

    submitted_by = _sanitize(submitted_by, _MAX_NAME_LEN)
    if not submitted_by:
        return None

    email = _sanitize(email, _MAX_EMAIL_LEN)
    if submitted_by == NON_MEMBER:
        if not email:
            return None
    else:
        # Members are identified by name; ignore any stray email value.
        email = ""

    row = {
        "ID": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "Submitted By": submitted_by,
        "User Email": email,
        "Feedback Type": feedback_type,
        "Message": message,
        "Status": "New",
    }

    df = _load()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_excel(df, FEEDBACK_FILE)
    return row


def _entries(feedback_type: str) -> list[dict]:
    df = _load()
    df = df[df["Feedback Type"] == feedback_type]
    df = df.sort_values("Timestamp", ascending=False)
    return df.to_dict("records")


def get_general_feedback() -> list[dict]:
    """Public feedback, newest first."""
    return _entries("General")


def get_feature_requests() -> list[dict]:
    """Admin-only feature requests, newest first."""
    return _entries("Feature Request")


def update_status(feedback_id: str, status: str) -> bool:
    """Update the Status of one entry (used for feature requests). Returns True on
    success, False for an unknown status or id."""
    if status not in STATUSES:
        return False
    df = _load()
    mask = df["ID"] == feedback_id
    if not mask.any():
        return False
    df.loc[mask, "Status"] = status
    save_excel(df, FEEDBACK_FILE)
    return True
