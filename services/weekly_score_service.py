"""
Weekly Score Upload session: data/WeeklyScoreSession.json

Replaces the old WhatsApp-based Sunday score submission with a transient,
self-service session. There is at most one session at a time:

    status "none"   -> nothing open; the page shows nothing to submit.
    status "open"    -> the score entry form is live; anyone can add/amend/
                        delete matches.
    status "closed"  -> admin has locked the list for review; read-only for
                        everyone until submitted to the league database, which
                        clears the session (back to "none") ready for next week.

See services/league_service.write_weekly_scores() for how a closed session's
matches get pushed into the annual league workbook.
"""
import csv
import json
import threading
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from config import Config
from services import r2_service
from services import spond_service
from services.league_service import get_league_roster, resolve_attendee_names, write_weekly_scores
from services.player_service import get_player_names

SESSION_PATH = Path(Config.DATA_DIR) / "WeeklyScoreSession.json"

VALID_SCORES = set(range(1, 31))
VALID_COURTS = set(range(1, 5))

# Guards every read-modify-write cycle on the session file. Render runs
# gunicorn with a single worker but 4 threads, all sharing this same process
# and file - without a lock, two near-simultaneous submissions (very plausible
# with 4-5 people entering scores at once on a Sunday) could both _load() the
# same "before" state, each append their own match, and the second _save()
# would silently overwrite the first, losing a submitted score with no error
# to anyone. Every function that reads and/or writes the session file must
# hold this lock for the whole cycle - _load()/_save() themselves don't
# acquire it (they're called by callers that already hold it, and this lock
# isn't reentrant). Not a substitute for the R2 upload staying off the
# critical path (see _save()) - this only serializes the fast local
# read-modify-write, not the background R2 push.
_session_lock = threading.Lock()

# A resubmission of the exact same match (same 4 players + scores, regardless
# of team order) within this window is treated as a duplicate tap/retry, not a
# genuine second match - see add_match().
RECENT_DUPLICATE_WINDOW = timedelta(seconds=15)


def _defaults():
    return {"status": "none", "date": None, "matches": []}


def _load():
    if not SESSION_PATH.exists():
        return _defaults()
    try:
        with open(SESSION_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _defaults()
    data.setdefault("status", "none")
    data.setdefault("date", None)
    data.setdefault("matches", [])
    return data


def _save(data):
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Fire-and-forget: r2_service.upload_file() is a blocking network call that
    # retries up to 3x with exponential-backoff sleeps on any hiccup, and this
    # path runs on every single add/amend/delete/open/close - on a busy Sunday
    # that's every request tying up a thread for however long R2 takes. Render
    # gives this app only 4 threads total, so a handful of concurrent or
    # duplicate-tap submissions blocking here starved every other page on the
    # site (Dashboard included), not just this one - see the 2026-09-08
    # Decisions Log entry. The local write above is already durable enough for
    # the live session (this is the only Render instance running), so a
    # briefly-eventually-consistent R2 copy is an acceptable trade for keeping
    # every request fast.
    threading.Thread(target=r2_service.upload_file, args=(SESSION_PATH,), daemon=True).start()


def default_session_date():
    """The Sunday a newly-opened session should default to: today if it's
    already Sunday, yesterday if today is Monday (entering the session that
    just finished the day before), otherwise the coming Sunday."""
    today = date.today()
    if today.weekday() == 6:  # Sunday
        return today
    if today.weekday() == 0:  # Monday
        return today - timedelta(days=1)
    return today + timedelta(days=(6 - today.weekday()) % 7)


def _duplicate_key(m):
    """Same four players (regardless of team order) + same two scores tied to
    their own team (regardless of which team is labelled 1 vs 2)."""
    pair_a = frozenset({m["p1"], m["p2"]})
    pair_b = frozenset({m["p3"], m["p4"]})
    return frozenset({(pair_a, m["score1"]), (pair_b, m["score2"])})


def _annotate(matches):
    counts = Counter(_duplicate_key(m) for m in matches)
    return [{**m, "is_duplicate": counts[_duplicate_key(m)] > 1} for m in matches]


def _historical_attendees(target_date):
    """Confirmed attendee {first_name, last_name} dicts for target_date, read
    from data/signups_history.csv (accepted RSVPs, ~6 months retained - see
    analytics_service.py) instead of a live Spond query. Once a Sunday has
    happened, attendance is settled - there's nothing to gain from hitting
    Spond live for it on every page poll, and a live query for an
    already-past date isn't something this app has been able to trust (see
    the 2026-09-08 Decisions Log entry this replaced: querying Spond live for
    a specific past Sunday could silently come back empty, falling through to
    the full club roster instead of that Sunday's actual attendees). This
    cache is exactly date-scoped from RSVP timestamps already fetched, so it
    doesn't have that problem. Returns [] if the cache has nothing for that
    date yet (e.g. too recent to have synced) - caller falls back to a live
    query in that case."""
    path = Path(Config.DATA_DIR) / "signups_history.csv"
    if not path.exists():
        return []
    attendees = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                start = datetime.fromisoformat(row.get("start") or "")
            except ValueError:
                continue
            if start.date() != target_date:
                continue
            first_name = (row.get("first_name") or "").strip()
            if not first_name:
                continue
            full_name = (row.get("full_name") or "").strip()
            last_name = full_name[len(first_name):].strip() if full_name.startswith(first_name) else ""
            key = row.get("member_id") or first_name
            attendees[key] = {"first_name": first_name, "last_name": last_name}
    return list(attendees.values())


def debug_player_sources(target_date):
    """Admin diagnostic: every data source in the dropdown-resolution chain
    for target_date, raw and resolved, so a live mismatch (e.g. an attendee
    missing or an unexpected name showing) can be pinpointed exactly instead
    of guessed at. Not used by the normal page - see the admin/debug-players
    route."""
    path = Path(Config.DATA_DIR) / "signups_history.csv"
    csv_total_rows = 0
    dates_present = set()
    date_rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                csv_total_rows += 1
                try:
                    start = datetime.fromisoformat(row.get("start") or "")
                except ValueError:
                    continue
                dates_present.add(start.date().isoformat())
                if start.date() == target_date:
                    date_rows.append({
                        "event_id": row.get("event_id"),
                        "event_heading": row.get("event_heading"),
                        "start": row.get("start"),
                        "member_id": row.get("member_id"),
                        "first_name": row.get("first_name"),
                        "full_name": row.get("full_name"),
                    })

    historical_raw = _historical_attendees(target_date)
    historical_resolved = resolve_attendee_names(target_date.year, historical_raw) if historical_raw else []

    live_raw = spond_service.get_confirmed_attendees(target_date)
    live_resolved = resolve_attendee_names(target_date.year, live_raw) if live_raw else []

    roster = get_league_roster(target_date.year)

    return {
        "target_date": target_date.isoformat(),
        "csv_total_rows": csv_total_rows,
        "csv_dates_present_recent": sorted(dates_present)[-15:],
        "csv_rows_for_date": date_rows,
        "historical_cache_raw": historical_raw,
        "historical_cache_resolved": historical_resolved,
        "live_spond_raw": live_raw,
        "live_spond_resolved": live_resolved,
        "league_roster": roster,
        "final_dropdown": _player_options(target_date),
    }


def _player_options(target_date):
    if target_date is None:
        return []
    if target_date <= date.today():
        # Already happened (or happening today) - prefer the settled,
        # exactly-dated history cache over a live query. See
        # _historical_attendees() for why.
        attendees = _historical_attendees(target_date)
        if attendees:
            return resolve_attendee_names(target_date.year, attendees)
    attendees = spond_service.get_confirmed_attendees(target_date)
    if attendees:
        return resolve_attendee_names(target_date.year, attendees)
    # Spond unreachable, or nobody's confirmed for that date yet - fall back
    # to the league roster. It's already in the club's short/nickname form
    # (e.g. "Tousif", not "Mohammad Tousif") - same as the Spond-resolved
    # path above - so names shown here don't flip to full "First Last" from
    # the member CSV depending on whether Spond happened to have data for
    # this date. Only fall further back to full names if there's no roster
    # yet at all (e.g. brand-new season, nothing else to offer).
    roster = get_league_roster(target_date.year)
    if roster:
        return sorted(roster, key=str.casefold)
    return sorted(get_player_names(), key=str.casefold)


def get_state():
    with _session_lock:
        data = _load()
    target_date = date.fromisoformat(data["date"]) if data.get("date") else None
    matches = sorted(data["matches"], key=lambda m: m["submitted_at"], reverse=True)
    return {
        "status": data["status"],
        "date": data["date"],
        "matches": _annotate(matches),
        "players": _player_options(target_date),
    }


def open_session(date_str):
    try:
        date.fromisoformat(date_str)
    except (TypeError, ValueError):
        raise ValueError("Please choose a valid date.")
    with _session_lock:
        data = _load()
        if data.get("date") != date_str:
            # A new date - start a fresh, empty session. (Re-opening the
            # *same* date, e.g. after an accidental Close, keeps whatever
            # matches are already there.)
            data = {"status": "open", "date": date_str, "matches": []}
        else:
            data["status"] = "open"
        _save(data)
    return data


def close_session():
    with _session_lock:
        data = _load()
        if data.get("status") != "open":
            raise ValueError("There's no open session to close.")
        data["status"] = "closed"
        _save(data)
    return data


def _validate_match(fields):
    p1 = (fields.get("p1") or "").strip()
    p2 = (fields.get("p2") or "").strip()
    p3 = (fields.get("p3") or "").strip()
    p4 = (fields.get("p4") or "").strip()
    try:
        score1 = int(fields.get("score1"))
        score2 = int(fields.get("score2"))
    except (TypeError, ValueError):
        raise ValueError("Scores must be numbers.")
    try:
        court_no = int(fields.get("court_no"))
    except (TypeError, ValueError):
        raise ValueError("Court No. is required.")
    if not all([p1, p2, p3, p4]):
        raise ValueError("All four players are required.")
    if len({p1, p2, p3, p4}) < 4:
        raise ValueError("The same player can't be in both teams.")
    if score1 not in VALID_SCORES or score2 not in VALID_SCORES:
        raise ValueError("Scores must be between 1 and 30.")
    if score1 == score2:
        raise ValueError("The two team scores can't be equal (someone has to win the buzzer).")
    if court_no not in VALID_COURTS:
        raise ValueError("Court No. must be between 1 and 4.")
    return {
        "court_no": court_no,
        "p1": p1, "p2": p2, "score1": score1,
        "p3": p3, "p4": p4, "score2": score2,
    }


def add_match(fields):
    match = _validate_match(fields)
    with _session_lock:
        data = _load()
        if data.get("status") != "open":
            raise ValueError("The session isn't open for entries right now.")

        # A repeated tap (or retry after a slow/no response) resubmitting the
        # exact same match within RECENT_DUPLICATE_WINDOW is a duplicate, not
        # a genuine second match - return the existing row instead of
        # creating another one. This is a server-side safety net independent
        # of the client-side submit lock (weekly_scores.js), which prevents
        # the same bug from a different angle (multiple devices, a retried
        # request, a slow response the client-side lock didn't cover). See
        # the 2026-09-08 Decisions Log entry for the incident this fixes.
        now = datetime.now()
        key = _duplicate_key(match)
        for m in data["matches"]:
            if _duplicate_key(m) != key:
                continue
            try:
                submitted = datetime.fromisoformat(m["submitted_at"])
            except ValueError:
                continue
            if now - submitted < RECENT_DUPLICATE_WINDOW:
                return m

        match["id"] = str(uuid.uuid4())
        match["submitted_at"] = now.isoformat()
        data["matches"].append(match)
        _save(data)
        return match


def amend_match(match_id, fields):
    updated = _validate_match(fields)
    with _session_lock:
        data = _load()
        if data.get("status") != "open":
            raise ValueError("The session isn't open for edits right now.")
        for m in data["matches"]:
            if m["id"] == match_id:
                updated["id"] = match_id
                updated["submitted_at"] = m["submitted_at"]
                m.clear()
                m.update(updated)
                _save(data)
                return m
        raise ValueError("That match no longer exists.")


def delete_match(match_id):
    with _session_lock:
        data = _load()
        if data.get("status") != "open":
            raise ValueError("The session isn't open for edits right now.")
        before = len(data["matches"])
        data["matches"] = [m for m in data["matches"] if m["id"] != match_id]
        if len(data["matches"]) == before:
            raise ValueError("That match no longer exists.")
        _save(data)


def submit_to_database():
    """Push the closed session's matches into the league workbook, then clear
    the session so the page is ready for next Sunday. Raises ValueError if the
    session isn't closed, has no date, or has no matches."""
    with _session_lock:
        data = _load()
        if data.get("status") != "closed":
            raise ValueError("Close the session first, then submit to the database.")
        if not data.get("date"):
            raise ValueError("No session date set.")
        if not data.get("matches"):
            raise ValueError("There are no scores to submit.")
        target_date = date.fromisoformat(data["date"])
        matches = sorted(data["matches"], key=lambda m: m["submitted_at"])

    # write_weekly_scores() writes to the league .xlsm - can take a while, and
    # deliberately runs outside the lock so it doesn't block get_state() polls
    # for its whole duration. Nothing else can mutate the session meanwhile:
    # every mutating function above requires status "open", and this session
    # is already "closed".
    count = write_weekly_scores(target_date, matches)

    with _session_lock:
        SESSION_PATH.unlink(missing_ok=True)
    r2_service.delete_file(SESSION_PATH)
    return count
