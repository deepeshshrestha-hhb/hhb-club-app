"""
Nepal Flood Relief charity drive.

Two small stores, both mirrored to R2 via the existing patterns:

  * data/charity_settings.json  - campaign on/off switch + fundraising target
    (same shape as committee_service's committee.json).
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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import Config
from services import r2_service
from services.excel_service import load_excel, save_excel

SETTINGS_PATH = Path(Config.DATA_DIR) / "charity_settings.json"
CONTRIBUTIONS_FILE = "CharityContributions.xlsx"

_COLUMNS = ["ID", "Timestamp", "Member Name", "Amount"]

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
    """All pledges, newest first."""
    df = _load_contributions()
    df = df.sort_values("Timestamp", ascending=False)
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
