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
    timestamps are present and positive, otherwise fall back to 1.0 hour, capped
    at MAX_EVENT_HOURS. Non-badminton Spond events (holidays, socials) are
    excluded by heading keyword and by venue, so a multi-day event like a club
    holiday trip can't inflate "Hours Played" (see EXCLUDE_KEYWORDS / VENUE_KEYWORDS).
  - Everything joins on full_name (resolved from the same Spond member list that
    backs hhb_members.csv), so there is no alias/first-name ambiguity here.
  - hhb_members.csv is rewritten wholesale on every Spond Refresh, so the hours
    live in a SEPARATE file that is merged at read time rather than added as
    columns to the member CSV.
"""
import asyncio
import csv
import datetime as _dt
import json
import logging
import os
import tempfile
import threading
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

# Only count events that are actually badminton sessions/tournaments at the
# club's two venues, not socials/trips organised through the same Spond group.
# Weekly sessions run 1hr, tournaments ~2hr, so 3hr comfortably covers both
# while still catching anything mis-scheduled as multi-day.
MAX_EVENT_HOURS = 3.0
EXCLUDE_KEYWORDS = ("holiday", "picnic")
VENUE_KEYWORDS = ("eastwood", "parklands")

_hours_cache = None


def _data_path(filename):
    return os.path.join(Config.DATA_DIR, filename)


def _atomic_write(path, write_fn):
    """Write a file via a same-directory temp file + os.replace(), so a
    concurrent reader (gunicorn runs multiple threads sharing this
    filesystem) always sees either the complete old file or the complete new
    one - never a truncated/partial one. Plain `open(path, "w")` truncates
    immediately and streams content out over time, which a request thread
    reading signups_history.csv or player_hours.csv mid-refresh could catch
    half-written, producing exactly the flickering "some players missing"
    symptom this replaced (the file always looked fine moments later, once
    the write finished - the signature of a race, not a data bug)."""
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(path) or ".", prefix=os.path.basename(path) + ".tmp"
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            write_fn(f)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# 1. Fetch signup history from Spond
# --------------------------------------------------------------------------- #

def _is_countable_event(ev, heading):
    """True if this Spond event should count toward Hours Played: a real
    badminton session/tournament at one of the club's two venues, not a
    social or trip (e.g. the annual club holiday) organised through the same
    Spond group."""
    heading_lower = heading.lower()
    if any(kw in heading_lower for kw in EXCLUDE_KEYWORDS):
        return False

    location = ev.get("location") or {}
    location_text = " ".join(
        str(location.get(key) or "") for key in ("feature", "address")
    ).lower()
    haystack = f"{heading_lower} {location_text}"
    return any(kw in haystack for kw in VENUE_KEYWORDS)


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
        heading = ev.get("heading", "") or ""
        if not _is_countable_event(ev, heading):
            continue

        start = _parse_timestamp(ev.get("startTimestamp"))
        end = _parse_timestamp(ev.get("endTimestamp"))
        if start is None:
            continue  # can't window an undated event
        if end is not None and end > start:
            duration = round((end - start).total_seconds() / 3600.0, 2)
        else:
            duration = 1.0  # club sessions are 1 hour; default when no end time
        duration = min(duration, MAX_EVENT_HOURS)

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


def _existing_row_count(csv_path):
    if not os.path.exists(csv_path):
        return 0
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))
    except OSError:
        return 0


def fetch_signups_history():
    """Fetch accepted-attendee signups for the last 6 months, overwrite the local
    data/signups_history.csv cache, and push it to R2. Fails silently (logs and
    keeps the existing cache) so an admin refresh never 500s on a Spond hiccup.

    Also refuses to overwrite with a suspiciously small result: a Spond fetch
    that comes back with far fewer rows than the cache already has is more
    likely a partial/rate-limited response (Spond "succeeding" but truncating)
    than a genuine drop in signups - there's no throttling or paging weirdness
    that would make a real 6-month history legitimately shrink by half
    overnight. Overwriting in that case would silently lose real history (this
    replaced a real incident: a refresh landed right after a Spond hiccup and
    wiped out an already-cached date's attendees with nothing to show for it).

    Returns the number of rows written on a genuine successful fetch (0 is a
    legitimate result for a brand-new season with nothing cached yet), or
    None if the fetch failed outright or was blocked by the guard above -
    callers MUST treat None as "the cache did not change" and must not mark
    the data as fresh (see the 2026-09-08 refresh_now() fix: this used to be
    conflated with a successful-but-empty fetch via a 0 return, which let a
    silently-failing Spond fetch get stamped as up to date indefinitely and
    masked weeks of real staleness behind a "refreshed" success message).
    """
    csv_path = _data_path(SIGNUPS_CSV)
    try:
        rows = asyncio.run(_fetch_signups_async())
    except Exception as exc:  # noqa: BLE001
        logger.error("Signup history fetch skipped (using cached CSV): %s", exc)
        return None

    existing = _existing_row_count(csv_path)
    if existing > 20 and len(rows) < existing * 0.5:
        logger.error(
            "Signup history fetch returned suspiciously few rows (%d vs %d "
            "cached) - keeping the existing cache instead of overwriting with "
            "what looks like a partial Spond response.", len(rows), existing,
        )
        return None

    def _write(f):
        writer = csv.DictWriter(f, fieldnames=SIGNUPS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    _atomic_write(csv_path, _write)
    logger.info("Signups: %d attendee rows written to %s", len(rows), csv_path)
    r2_service.upload_file(csv_path)
    return len(rows)


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

    def _write(f):
        writer = csv.writer(f)
        writer.writerow(["full_name", "hours_last_four_weeks", "hours_last_six_months"])
        for name in sorted(totals, key=str.casefold):
            t = totals[name]
            writer.writerow([
                name,
                round(t["hours_last_four_weeks"], 1),
                round(t["hours_last_six_months"], 1),
            ])

    _atomic_write(hours_path, _write)
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


# --------------------------------------------------------------------------- #
# 4. Club analytics (demographics, tenure, activity) for the Analytics tab
# --------------------------------------------------------------------------- #

AGE_BANDS = [
    ("Under 18", lambda a: a < 18),
    ("18–29", lambda a: 18 <= a <= 29),
    ("30–39", lambda a: 30 <= a <= 39),
    ("40–49", lambda a: 40 <= a <= 49),
    ("50+", lambda a: a >= 50),
]


def get_club_analytics(players, top_n=5):
    """Aggregate club-level insights from the already-merged players list (which
    carries age + hours) plus profile data (year joined). Pure computation, no I/O
    beyond reading the profiles file."""
    from services import profile_service  # local import avoids any import cycle

    # --- Age demographics ---
    ages = [p["age"] for p in players if p.get("age")]
    bands = [
        {"label": label, "count": sum(1 for a in ages if pred(a))}
        for label, pred in AGE_BANDS
    ]
    age = {
        "average": round(sum(ages) / len(ages), 1) if ages else None,
        "known": len(ages),
        "unknown": len(players) - len(ages),
        "bands": bands,
        "max_band": max((b["count"] for b in bands), default=0),
    }

    # --- Activity (last 6 months) ---
    def h6(p):
        return p.get("hours_last_six_months", 0) or 0

    ranked = sorted(players, key=h6, reverse=True)
    most_hours = [p for p in ranked if h6(p) > 0][:top_n]
    inactive = sorted(
        (p for p in players if h6(p) == 0),
        key=lambda p: p["full_name"].casefold(),
    )

    # --- Club tenure (longest-serving, from profile "year joined") ---
    current_year = _dt.date.today().year
    serving = []
    for slug, prof in profile_service.get_all_profiles().items():
        yj = str(prof.get("year_joined", "")).strip()
        if not yj.isdigit():
            continue
        year = int(yj)
        if year < 1990 or year > current_year:
            continue
        serving.append({
            "full_name": prof.get("full_name", ""),
            "slug": slug,
            "year_joined": year,
            "years": current_year - year,
        })
    serving.sort(key=lambda x: (x["year_joined"], x["full_name"].casefold()))

    return {
        "age": age,
        "most_hours": most_hours,
        "inactive": inactive,
        "inactive_count": len(inactive),
        "longest_serving": serving[:top_n],
        "has_hours": any(h6(p) > 0 for p in players),
    }


# --------------------------------------------------------------------------- #
# 5. Lazy auto-refresh — throttled background refresh triggered on page load
# --------------------------------------------------------------------------- #
#
# Visiting the Players or Calendar page calls maybe_refresh_async(): if the
# signup data is missing or older than STALE_AFTER, it kicks off a refresh in a
# daemon thread so the page never blocks on the ~6-month Spond fetch.
#
# Staleness is judged from a persisted last-fetched timestamp in
# signups_meta.json (read by CONTENT, not file mtime) because r2_service resets
# local file mtimes on every Render cold-start download.

META_FILE = "signups_meta.json"
STALE_AFTER = timedelta(days=7)
MIN_RETRY = timedelta(hours=1)  # don't re-attempt within this window after a try

_refresh_lock = threading.Lock()
_refreshing = False
_last_attempt = None  # in-process: last time we kicked off (or tried) a refresh


def _meta_path():
    return _data_path(META_FILE)


def _read_last_fetched():
    """Persisted last-fetched datetime (tz-aware), or None. Read from file
    content so it survives R2 round-trips (which reset mtimes)."""
    path = _meta_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return _parse_iso(json.load(f).get("last_fetched"))
    except (json.JSONDecodeError, OSError, AttributeError):
        return None


def _write_last_fetched():
    path = _meta_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_fetched": datetime.now(LOCAL_TZ).isoformat()}, f)
        r2_service.upload_file(path)
    except OSError as exc:  # noqa: BLE001
        logger.warning("Could not write signups meta: %s", exc)


def _spond_configured():
    return bool(Config.SPOND_USERNAME and Config.SPOND_PASSWORD and Config.SPOND_GROUP_ID)


def refresh_now():
    """Fetch signups + aggregate hours. Used by both the admin button and the
    background auto-refresh. Returns {"signups_fetched", "hours_players"}:
    "signups_fetched" is the row count on a genuine successful Spond fetch, or
    None if the fetch failed or was blocked (see fetch_signups_history) -
    "hours_players" (aggregate_hours's per-member count) is computed either
    way, since it's just a recompute over whatever signups_history.csv
    already has, stale or not.

    last-fetched is only stamped when signups_fetched is not None. Stamping
    it unconditionally (the previous behaviour) meant a Spond fetch that kept
    silently failing or getting guard-blocked would still mark the cache as
    fresh - hiding real staleness behind a "refreshed" message and stalling
    the 7-day background auto-refresh from ever retrying, since as far as it
    could tell nothing was overdue. This was the actual root cause of the
    Weekly Score Upload dropdown reading weeks-stale attendance while every
    refresh attempt reported success (see the matching 2026-09-08 Decisions
    Log entry)."""
    signups_fetched = fetch_signups_history()
    hours_players = aggregate_hours()
    if signups_fetched is not None:
        _write_last_fetched()
    return {"signups_fetched": signups_fetched, "hours_players": hours_players}


def _is_stale():
    last = _read_last_fetched()
    if last is None:
        return True
    return (datetime.now(LOCAL_TZ) - last) > STALE_AFTER


def _background_refresh():
    global _refreshing
    try:
        result = refresh_now()
        if result["signups_fetched"] is None:
            logger.warning(
                "Auto-refresh: signup history fetch did NOT update (still "
                "stale - see the error above) - hours recomputed for %d "
                "cached players, last-fetched left unstamped so this retries.",
                result["hours_players"],
            )
        else:
            logger.info(
                "Auto-refresh of signup analytics complete (%d signup rows, "
                "%d players).", result["signups_fetched"], result["hours_players"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Auto-refresh of signup analytics failed: %s", exc)
    finally:
        _refreshing = False


def maybe_refresh_async():
    """If signup data is missing or older than STALE_AFTER (7 days), refresh it
    in a daemon thread. Non-blocking, at most one refresh at a time, and
    throttled (MIN_RETRY) so a failing Spond can't cause a retry storm. No-op
    when Spond isn't configured (e.g. local dev without creds)."""
    global _refreshing, _last_attempt
    if not _spond_configured():
        return
    now = datetime.now(LOCAL_TZ)
    if _last_attempt is not None and (now - _last_attempt) < MIN_RETRY:
        return
    if not _is_stale():
        return
    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True
        _last_attempt = now
    threading.Thread(target=_background_refresh, daemon=True).start()
