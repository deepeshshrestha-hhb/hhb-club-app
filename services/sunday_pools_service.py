"""
Sunday Pool Play: data/sunday_pools.json

Per the committee's new 10-11am format, the second half of the Sunday
session is split into two pools by the current Club Rankings
(club_rankings_service): Pool A (top half, Courts 1-2) and Pool B (bottom
half, Courts 3-4). An admin picks a date and generates that Sunday's pools
from whoever's actually confirmed for the 10-11am session, publishing the
result to /sunday-pools for everyone to check before turning up. The 9-10am
half of the session is unaffected and continues as normal open play.

Storage: {"pools": {"<YYYY-MM-DD>": {"pool_a": [...], "pool_b": [...],
"unranked": [...], "generated_at": iso}}}, keyed by ISO date so a past
week's pools stay available (re-generating the same date overwrites it).
The public page shows the most recently generated date unless a specific
one is requested.
"""
import csv
import json
from datetime import date, datetime
from pathlib import Path

from config import Config
from services import r2_service
from services import spond_service
from services import club_rankings_service

POOLS_PATH = Path(Config.DATA_DIR) / "sunday_pools.json"

# The Sunday Pool Play format only splits the 10-11am half of the session
# (see the "Sunday Pool Play" Club Rules section for the full write-up) -
# 9-10am continues as normal open play, unaffected.
POOL_HOUR = 10


def _load() -> dict:
    if not POOLS_PATH.exists():
        return {"pools": {}}
    try:
        with open(POOLS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"pools": {}}
    data.setdefault("pools", {})
    return data


def _save(data: dict):
    POOLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(POOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(POOLS_PATH)


def _historical_attendees_10_11(target_date) -> list[str]:
    """Confirmed full names for target_date's 10-11am session only, from
    data/signups_history.csv (accepted RSVPs, ~6 months retained - see
    analytics_service.py). Mirrors weekly_score_service._historical_attendees
    but scoped to POOL_HOUR specifically, since Pool Play only concerns the
    second half of the session."""
    path = Path(Config.DATA_DIR) / "signups_history.csv"
    if not path.exists():
        return []
    names = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                start = datetime.fromisoformat(row.get("start") or "")
            except ValueError:
                continue
            if start.date() != target_date or start.hour != POOL_HOUR:
                continue
            full_name = (row.get("full_name") or "").strip()
            if full_name:
                names[row.get("member_id") or full_name] = full_name
    return sorted(names.values(), key=str.casefold)


def _attendees_for_pools(target_date) -> list[str]:
    """Full names of everyone confirmed for target_date's 10-11am session.
    Historical-cache-first for a date that's today-or-earlier (settled, and
    avoids hammering Spond live for an already-decided attendance list - see
    weekly_score_service._historical_attendees for the reasoning this
    mirrors); a live Spond query otherwise (or as a fallback if the cache has
    nothing yet, e.g. too recent to have synced)."""
    if target_date <= date.today():
        names = _historical_attendees_10_11(target_date)
        if names:
            return names
    raw = spond_service.get_confirmed_attendees_for_hour(target_date, POOL_HOUR)
    names = {
        f"{a['first_name']} {a['last_name']}".strip()
        for a in raw if (a.get("first_name") or "").strip()
    }
    return sorted(names, key=str.casefold)


def generate_pools(date_str: str) -> dict:
    """Generate and publish Pool A / Pool B for date_str's 10-11am session.
    Raises ValueError for an invalid date or if nobody's confirmed yet.

    Ranking comes from club_rankings_service's current order: attendees who
    are in that list are sorted by rank (best first); anyone not yet ranked
    (e.g. a recently-joined player) is appended after, alphabetically - so
    they land in Pool B by default unless there aren't enough ranked
    attendees to fill Pool A on their own. The combined list is then simply
    cut in half - top half is Pool A, bottom half Pool B - giving Pool A the
    extra player on an odd-numbered turnout."""
    try:
        target_date = date.fromisoformat(date_str)
    except (TypeError, ValueError):
        raise ValueError("Please choose a valid date.")

    attendees = _attendees_for_pools(target_date)
    if not attendees:
        raise ValueError(
            "No confirmed 10-11am sign-ups found for that date yet - try again "
            "closer to the day, or check Spond sign-ups directly."
        )

    ranked_players = club_rankings_service.get_rankings()["players"]
    rank_of = {name: i for i, name in enumerate(ranked_players)}

    ranked_attendees = sorted((a for a in attendees if a in rank_of), key=lambda a: rank_of[a])
    unranked_attendees = sorted((a for a in attendees if a not in rank_of), key=str.casefold)
    ordered = ranked_attendees + unranked_attendees

    half = (len(ordered) + 1) // 2  # odd turnout -> Pool A gets the extra player
    pool_a = ordered[:half]
    pool_b = ordered[half:]

    data = _load()
    data["pools"][date_str] = {
        "pool_a": pool_a,
        "pool_b": pool_b,
        "unranked": unranked_attendees,
        "generated_at": datetime.now().isoformat(),
    }
    _save(data)
    return data["pools"][date_str]


def get_pools_for_date(date_str: str):
    return _load()["pools"].get(date_str)


def get_latest_pools():
    """Returns (date_str, pools_dict) for the most recently generated date,
    or (None, None) if nothing's been generated yet."""
    pools = _load()["pools"]
    if not pools:
        return None, None
    latest = max(pools)
    return latest, pools[latest]


def list_generated_dates() -> list[str]:
    """All generated dates, most recent first."""
    return sorted(_load()["pools"], reverse=True)
