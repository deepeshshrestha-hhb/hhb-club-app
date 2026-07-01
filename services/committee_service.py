"""
HHB Committee roster: data/committee.json

Stores whether the Committee tab is shown on the About page, plus each
member's editable card text and the linked player name whose profile photo
(from profile_service) is shown on the card.
"""
import json
from pathlib import Path

from config import Config
from services import r2_service

COMMITTEE_PATH = Path(Config.DATA_DIR) / "committee.json"

DEFAULT_MEMBERS = [
    {
        "id": "1", "roster_no": "NO. 1", "name": "Rukhsar Ahmed",
        "linked_player": "Rukhsar Ahmed", "badge": "Founder & President",
        "title_line": "The Shuttle Sultan",
        "desc": "Most respected voice in the club. Founding member. Final word on all things HHB.",
        "founder": True,
    },
    {
        "id": "2", "roster_no": "NO. 2", "name": "Deepak Tejwani",
        "linked_player": "Deepak Tejwani", "badge": "Founder Member",
        "title_line": "The Net Judge",
        "desc": "Founding member with the most practical, level head in every decision.",
        "founder": True,
    },
    {
        "id": "3", "roster_no": "NO. 3", "name": "Jalal Miah",
        "linked_player": "Jalal Miah", "badge": "Senior Committee Member",
        "title_line": "The Smash Strategist",
        "desc": "Rukhsar's right hand. Balanced, unafraid to challenge the norm — the think tank behind every call.",
        "founder": False,
    },
    {
        "id": "4", "roster_no": "NO. 4", "name": "Prasanna Venkatesan",
        "linked_player": "Prasanna Venkatesan", "badge": "Senior Committee Member",
        "title_line": "The Rally Realist",
        "desc": "Senior member with a grounded, no-nonsense take on club matters.",
        "founder": False,
    },
    {
        "id": "5", "roster_no": "NO. 5", "name": "Deepesh Shrestha",
        "linked_player": "Deepesh Shrestha", "badge": "Tournaments, Events & Website",
        "title_line": "The Bracket Architect",
        "desc": "Runs every tournament and event, and keeps the club's digital courts online.",
        "founder": False,
    },
    {
        "id": "6", "roster_no": "NO. 6", "name": "Thomas Jose",
        "linked_player": "Thomas Jose", "badge": "Treasurer and Accounts Manager",
        "title_line": "The Debt Smasher",
        "desc": "Splitwise-meets-Spond wizardry to track who owes what — and the innovative name-and-shame lists to prove it.",
        "founder": False,
    },
]


def _defaults() -> dict:
    return {"visible": True, "members": json.loads(json.dumps(DEFAULT_MEMBERS))}


def _load() -> dict:
    if not COMMITTEE_PATH.exists():
        return _defaults()
    try:
        with open(COMMITTEE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _defaults()
    data.setdefault("visible", True)
    data.setdefault("members", DEFAULT_MEMBERS)
    return data


def _save(data: dict):
    COMMITTEE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMITTEE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(COMMITTEE_PATH)


def get_committee() -> dict:
    """Returns {"visible": bool, "members": [...]}."""
    return _load()


def is_visible() -> bool:
    return bool(_load().get("visible", True))


def set_visible(visible: bool):
    data = _load()
    data["visible"] = bool(visible)
    _save(data)


def update_member(member_id: str, fields: dict) -> bool:
    """Update one committee member's card text. Returns False if the id is unknown."""
    data = _load()
    for m in data["members"]:
        if m["id"] == member_id:
            m["roster_no"] = (fields.get("roster_no") or m["roster_no"]).strip()
            m["name"] = (fields.get("name") or m["name"]).strip()
            m["linked_player"] = (fields.get("linked_player") or m["name"]).strip()
            m["badge"] = (fields.get("badge") or "").strip()
            m["title_line"] = (fields.get("title_line") or "").strip()
            m["desc"] = (fields.get("desc") or "").strip()
            m["founder"] = fields.get("founder") in ("on", "true", "1", True)
            _save(data)
            return True
    return False
