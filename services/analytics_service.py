"""
Player signup analytics derived from Spond events (not tournament results).

Pipeline:
  1. fetch_signups_history()  - pull the last ~6 months of Spond events, keep only
     accepted attendees, resolve member ids -> names, and write the cleaned rows
     to data/signups_history.csv (then push to R2).
  2. aggregate_hours()        - read that cache and compute hours played per player
     in two windows (last 4 weeks, last 6 months), writing data/player_hours.csv.
  3. get_player_hours()       - read player_hours.csv into a cached dict that
     player_service merges into each player record.

Design notes:
  - "Attended" == accepted the RSVP (responses.acceptedIds); declined/unconfirmed/
    waiting-list are excluded. The club does not record reliable check-in data, so
    no-shows cannot be distinguished from accepted attendees.
  - Each session is 1 hour at this club, so we use (end - start) when both
    timestamps are present and positive, otherwise fall back to 1.0 hour.
  - Everything joins on full_name (resolved from the same Spond member list that
    backs hhb_members.csv), so there is no alias/first-name ambiguity here.
  - hhb_members.csv is rewritten wholesale on every Spond Refresh, so the hours
    live in a SEPARATE file that is merged at read time rather than added as
    columns to the member CSV.
"""
import asyncio
import csv
import logging
import os
from datetime import datetime, timedelta

from config import Config
from services import r2_service
from services.spond_service import _parse_timestamp, LOCAL_TZ

try:
    from spond import spond
except ImportError:
    spond = None

logger = logging.getLogger("analytics")

SIGNUPS_CSV = "signups_history.csv"
HOURS_CSV = "player_hours.csv"
MEMBERS_CSV = "hhb_members.csv"

SIGNUPS_FIELDS = [
    "event_id", "event_heading", "start", "end",
    "duration_hours", "member_id", "first_name", "full_name",
]

# Time windows (days). ~6 months and 4 weeks.
SIX_MONTHS_DAYS = 183
FOUR_WEEKS_DAYS = 28

_hours_cache = None


def _data_path(filename):
    return os.path.join(Config.DATA_DIR, filename)


# --------------------------------------------------------------------------- #
# 1. Fetch signup history from Spond
# --------------------------------------------------------------------------- #

async def _fetch_signups_async():
    """Fetch the last ~6 months of Spond events and return one row per accepted
    attendee, with the session duration resolved (defaulting to 1 hour)."""
    if spond is None:
        raise RuntimeError("The 'spond' package is not installed. Run: pip install spond")

    username = Config.SPOND_USERNAME
    password = Config.SPOND_PASSWORD
    group_id = Config.SPOND_GROUP_ID
    if not username or "your_email" in username:
        raise RuntimeError("Spond credentials are not set (SPOND_USERNAME/PASSWORD/GROUP_ID).")

    s = spond.Spond(username=username, password=password)
    try:
        max_start = datetime.now()
        min_start = max_start - timedelta(days=SIX_MONTHS_DAYS)
        # max_events default in the spond lib is 100; raise it so 6 months of
        # roughly-weekly sessions aren't truncated.
        events = await s.get_events(
            group_id=group_id,
            min_start=min_start,
            max_start=max_start,
            include_scheduled=True,
            max_events=1000,
        )
        members = await _fetch_member_map(s, group_id)
    finally:
        await s.clientsession.close()

    rows = []
    for ev in events or []:
        start = _parse_timestamp(ev.get("startTimestamp"))
        end = _parse_timestamp(ev.get("endTimestamp"))
        if start is None:
            continue  # can't window an undated event
        if end is not None and end > start:
            duration = round((end - start).total_seconds() / 3600.0, 2)
        else:
            duration = 1.0  # club sessions are 1 hour; default when no end time

        responses = ev.get("responses") or {}
        accepted = responses.get("acceptedIds") or []
        for member_id in accepted:
            member = members.get(member_id)
            if not member:
                continue  # unknown / ex-member id we can't attribute
            rows.append({
                "event_id": ev.get("id", ""),
                "event_heading": ev.get("heading", ""),
                "start": start.isoformat(),
                "end": end.isoformat() if end else "",
                "duration_hours": duration,
                "member_id": member_id,
                "first_name": member["first_name"],
                "full_name": member["full_name"],
            })
    return rows


async def _fetch_member_map(s, group_id):
    """Return {member_id: {"first_name", "full_name"}} for the group."""
    try:
        group = await s.get_group(group_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Spond member lookup failed: %s", exc)
        return {}
    out = {}
    for m in group.get("members", []) or []:
        mid = m.get("id")
        if not mid:
            continue
        first = m.get("firstName", "") or ""
        last = m.get("lastName", "") or ""
        out[mid] = {
            "first_name": first,
            "full_name": f"{first} {last}".strip(),
        }
    return out


def fetch_signups_history():
    """Fetch accepted-attendee signups for the last 6 months, overwrite the local
    data/signups_history.csv cache, and push it to R2. Fails silently (logs and
    keeps the existing cache) so an admin refresh never 500s on a Spond hiccup."""
    csv_path = _data_path(SIGNUPS_CSV)
    try:
        rows = asyncio.run(_fetch_signups_async())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SIGNUPS_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Signups: %d attendee rows written to %s", len(rows), csv_path)
        r2_service.upload_file(csv_path)
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.error("Signup history fetch skipped (using cached CSV): %s", exc)
        return 0


# --------------------------------------------------------------------------- #
# 2. Aggregate hours per player
# --------------------------------------------------------------------------- #

def _member_full_names():
    """All current member full names from hhb_members.csv (so players with no
    signups still get a 0-hour row)."""
    path = _data_path(MEMBERS_CSV)
    names = []
    if not os.path.exists(path):
        return names
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("full_name") or "").strip()
            if name:
                names.append(name)
    return names


def aggregate_hours():
    """Read data/signups_history.csv and write data/player_hours.csv with
    hours_last_four_weeks and hours_last_six_months per player. Every current
    member is seeded at 0 so the inactive-players view is correct."""
    signups_path = _data_path(SIGNUPS_CSV)
    hours_path = _data_path(HOURS_CSV)

    now = datetime.now(LOCAL_TZ)
    six_months_ago = now - timedelta(days=SIX_MONTHS_DAYS)
    four_weeks_ago = now - timedelta(days=FOUR_WEEKS_DAYS)

    # Seed every member at zero.
    totals = {
        name: {"hours_last_four_weeks": 0.0, "hours_last_six_months": 0.0}
        for name in _member_full_names()
    }

    if os.path.exists(signups_path):
        with open(signups_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                full_name = (row.get("full_name") or "").strip()
                if not full_name:
                    continue
                start = _parse_iso(row.get("start"))
                if start is None or start < six_months_ago:
                    continue
                try:
                    duration = float(row.get("duration_hours") or 0)
                except ValueError:
                    duration = 0.0
                bucket = totals.setdefault(
                    full_name,
                    {"hours_last_four_weeks": 0.0, "hours_last_six_months": 0.0},
                )
                bucket["hours_last_six_months"] += duration
                if start >= four_weeks_ago:
                    bucket["hours_last_four_weeks"] += duration

    with open(hours_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["full_name", "hours_last_four_weeks", "hours_last_six_months"])
        for name in sorted(totals, key=str.casefold):
            t = totals[name]
            writer.writerow([
                name,
                round(t["hours_last_four_weeks"], 1),
                round(t["hours_last_six_months"], 1),
            ])
    logger.info("Player hours written for %d players to %s", len(totals), hours_path)
    r2_service.upload_file(hours_path)
    invalidate_cache()
    return len(totals)


def _parse_iso(value):
    """Parse an ISO timestamp string (tz-aware) back to a LOCAL_TZ datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


# --------------------------------------------------------------------------- #
# 3. Read cached hours (merged into player records by player_service)
# --------------------------------------------------------------------------- #

def invalidate_cache():
    """Drop the in-process player-hours cache. Called after aggregate_hours()
    and by the admin refresh action."""
    global _hours_cache
    _hours_cache = None


def get_player_hours():
    """Return {full_name: {"hours_last_four_weeks", "hours_last_six_months"}},
    cached in-process. Empty dict if the file is missing."""
    global _hours_cache
    if _hours_cache is not None:
        return _hours_cache

    path = _data_path(HOURS_CSV)
    result = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("full_name") or "").strip()
                if not name:
                    continue
                result[name] = {
                    "hours_last_four_weeks": _to_float(row.get("hours_last_four_weeks")),
                    "hours_last_six_months": _to_float(row.get("hours_last_six_months")),
                }
    _hours_cache = result
    return result


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
