"""
Event summary service.

Stores an admin-authored overview paragraph for each event that has a photo
gallery (a tournament year, the annual picnic, etc.). The summary is shown to
all users at the top of the event's photo gallery; only admins can edit it.

Keyed by the same ``event_id`` the photos use (e.g. ``doubles_2025``,
``league_2024``, ``annual_picnic_2025``). Metadata lives in
data/EventSummaries.xlsx and is mirrored to R2 via the shared
load_excel/save_excel helpers (durable storage with a local cache), so this
reuses the proven Excel + R2 pattern rather than introducing a database.

Sheet schema:
    event_id | summary | updated_date
"""
from datetime import datetime, timezone

import pandas as pd

from services.excel_service import load_excel, save_excel

SUMMARIES_FILE = "EventSummaries.xlsx"

_COLUMNS = ["event_id", "summary", "updated_date"]

_MAX_SUMMARY_LEN = 5000


def _load() -> pd.DataFrame:
    df = load_excel(SUMMARIES_FILE)
    if df.empty:
        return pd.DataFrame(columns=_COLUMNS)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[_COLUMNS].fillna("")


def _sanitize(text: str) -> str:
    """Trim whitespace, drop control characters (keep newlines/tabs), cap length.
    Jinja autoescaping handles XSS-safe display, so we store cleaned plain text."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    return cleaned.strip()[:_MAX_SUMMARY_LEN]


def get_summary(event_id: str) -> str:
    """Return the saved summary text for an event, or '' if none."""
    event_id = (event_id or "").strip()
    if not event_id:
        return ""
    df = _load()
    match = df[df["event_id"] == event_id]
    if match.empty:
        return ""
    value = str(match["summary"].iloc[0])
    return "" if value == "nan" else value


def save_summary(event_id: str, summary: str) -> bool:
    """Insert or update the summary for an event. An empty/blank summary removes
    the row. Returns True on success, False for a missing event_id."""
    event_id = (event_id or "").strip()
    if not event_id:
        return False

    summary = _sanitize(summary)
    df = _load()
    mask = df["event_id"] == event_id

    if not summary:
        # Blank submission clears any existing summary.
        if mask.any():
            df = df[~mask].reset_index(drop=True)
            save_excel(df, SUMMARIES_FILE)
        return True

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if mask.any():
        df.loc[mask, "summary"] = summary
        df.loc[mask, "updated_date"] = now
    else:
        row = {"event_id": event_id, "summary": summary, "updated_date": now}
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    save_excel(df, SUMMARIES_FILE)
    return True
