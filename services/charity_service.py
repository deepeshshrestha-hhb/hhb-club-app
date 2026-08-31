"""
Nepal Flood Relief charity drive.

Three small stores, all mirrored to R2 via the existing patterns:

  * data/charity_settings.json  - campaign on/off switch + fundraising target
    (same shape as committee_service's committee.json).
  * data/charity_content.json   - admin-editable freeform text for the top
    write-up and the "How to Contribute" (bank details) section, so wording
    tweaks don't need a redeploy (same pattern as about_content_service.py).
  * data/CharityContributions.xlsx - the pledge ledger (ID, Timestamp, Member
    Name, Amount), loaded/saved via the shared load_excel/save_excel helpers
    used by feedback_service.

Members pledge by picking their name from the club player list and entering an
amount - the same no-login, name-picker trust model as the Feedback form.
Pledges are logged here; the actual bank transfers happen outside the app
(the page displays the account details to transfer to), and the club then
makes one combined donation via JustGiving.
"""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from markupsafe import Markup, escape

from config import Config
from services import r2_service
from services.excel_service import load_excel, save_excel

# Matches either a markdown-style [label](url) link or a bare http(s):// URL,
# so an admin can either paste a raw link or write `[HExN](https://...)` to
# keep the link text tidy - no rich text editor needed.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)|(https?://[^\s<]+)")


def linkify(text: str) -> Markup:
    """Escape freeform admin-edited text, then turn markdown-style links and
    bare URLs into clickable <a> tags."""
    escaped = str(escape(text or ""))

    def repl(m):
        if m.group(2):
            label, url = m.group(1), m.group(2)
        else:
            url = label = m.group(3)
        return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'

    return Markup(_LINK_RE.sub(repl, escaped))

SETTINGS_PATH = Path(Config.DATA_DIR) / "charity_settings.json"
CONTENT_PATH = Path(Config.DATA_DIR) / "charity_content.json"
CONTRIBUTIONS_FILE = "CharityContributions.xlsx"

CONTENT_KEYS = ("blurb", "how_to_contribute")

DEFAULT_CONTENT = {
    "blurb": (
        "Nepal has been hit by severe flash floods, with communities in areas "
        "like Trishuli among the hardest affected. One of our own HHB "
        "Committee members is from Nepal, and as a club we want to help in "
        "every way we can.\n\n"
        "No amount is too small — every pound helps.\n\n"
        "We're raising money for [HExN](https://www.facebook.com/hexnepal), a "
        "charity that has been working for Nepal since 2008 and has relief "
        "efforts ongoing right now for people affected in areas like "
        "Trishuli. The full amount raised through this page will be donated "
        "in one combined contribution via HHB Club's "
        "[JustGiving campaign page](https://www.justgiving.com/campaign/nepal2026?utm_medium=CA&utm_source=CL).\n\n"
        "Rather than everyone donating individually, please transfer your "
        "contribution to the club and add it below — we'll make one "
        "combined donation on JustGiving and share proof with everyone."
    ),
    "how_to_contribute": (
        "Transfer your contribution to:\n\n"
        "Name: Deepesh Shrestha\n"
        "Account No.: 30550270\n"
        "Sort Code: 60-30-30\n\n"
        "Once you've transferred, add your name and amount below so it "
        "shows on the running total."
    ),
}

_COLUMNS = ["ID", "Timestamp", "Member Name", "Amount"]

# Dropdown sentinel for "Other" - lets non-members and members no longer
# active in Spond (so absent from the player list) type their own name.
OTHER_OPTION = "__other__"

_MAX_NAME_LEN = 120
_MAX_AMOUNT = 10000  # sanity cap on a single pledge, not a hard business rule

_DEFAULT_SETTINGS = {"is_open": True, "target_amount": 750}


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_SETTINGS)
    data.setdefault("is_open", True)
    data.setdefault("target_amount", 750)
    return data


def _save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(SETTINGS_PATH)


def get_settings() -> dict:
    """Returns {"is_open": bool, "target_amount": float}."""
    return _load_settings()


def set_open(is_open: bool):
    data = _load_settings()
    data["is_open"] = bool(is_open)
    _save_settings(data)


def set_target(amount) -> bool:
    """Update the fundraising target. Returns False for an invalid amount."""
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    data = _load_settings()
    data["target_amount"] = amount
    _save_settings(data)
    return True


def _load_content() -> dict:
    if not CONTENT_PATH.exists():
        return dict(DEFAULT_CONTENT)
    try:
        with open(CONTENT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONTENT)
    for key, default_val in DEFAULT_CONTENT.items():
        data.setdefault(key, default_val)
    return data


def _save_content(data: dict):
    CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(CONTENT_PATH)


def get_content() -> dict:
    """Returns {"blurb": str, "how_to_contribute": str}."""
    return _load_content()


def update_content_section(key: str, text: str) -> bool:
    """Update one freeform content section. Returns False for an unknown key."""
    if key not in CONTENT_KEYS:
        return False
    data = _load_content()
    data[key] = (text or "").strip()
    _save_content(data)
    return True


def _load_contributions() -> pd.DataFrame:
    df = load_excel(CONTRIBUTIONS_FILE)
    if df.empty:
        return pd.DataFrame(columns=_COLUMNS)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[_COLUMNS].fillna("")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    return df


def get_contributions() -> list[dict]:
    """All pledges, oldest first (so the numbered list on the page starts with
    the first person to contribute)."""
    df = _load_contributions()
    df = df.sort_values("Timestamp", ascending=True)
    return df.to_dict("records")


def get_total() -> float:
    df = _load_contributions()
    return round(float(df["Amount"].sum()), 2)


def add_contribution(member_name: str, amount) -> dict | None:
    """Validate and persist one pledge. Returns the stored row dict, or None for
    an invalid submission (no name selected, or a non-positive/absurd amount)."""
    member_name = (member_name or "").strip()[:_MAX_NAME_LEN]
    if not member_name:
        return None

    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return None
    if amount <= 0 or amount > _MAX_AMOUNT:
        return None

    row = {
        "ID": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "Member Name": member_name,
        "Amount": amount,
    }

    df = _load_contributions()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_excel(df, CONTRIBUTIONS_FILE)
    return row


def delete_contribution(contribution_id: str) -> bool:
    """Delete one pledge by ID. Returns True on success, False when unknown."""
    contribution_id = (contribution_id or "").strip()
    if not contribution_id:
        return False
    df = _load_contributions()
    mask = df["ID"] == contribution_id
    if not mask.any():
        return False
    df = df[~mask].reset_index(drop=True)
    save_excel(df, CONTRIBUTIONS_FILE)
    return True
