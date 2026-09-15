"""
Player Ranking Vote: data/player_votes.json

Lets club members vote on their own Top 10 (ranked) from the club's current
Top 20 (per Club Rankings), identity confirmed via a name dropdown - no
login. One vote per member, overwritten in place on resubmission. Storage
follows weekly_score_service.py's JSON pattern (lock-guarded read-modify-
write, backgrounded R2 upload) rather than an Excel workbook - the closest
Excel precedent, Feedback.xlsx, is append-only and has no clean way to
overwrite-by-submitter or hold admin flags alongside the rows.

See routes/vote_routes.py for the /vote and /vote/results pages.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import Config
from services import r2_service
from services.club_rankings_service import get_rankings
from services.player_service import get_player_names

VOTES_PATH = Path(Config.DATA_DIR) / "player_votes.json"

TOP_N = 20
PICK_N = 10

# Guards every read-modify-write cycle on the votes file - same rationale as
# weekly_score_service._session_lock: Render runs one gunicorn worker with 4
# threads sharing this same file, so two near-simultaneous submissions could
# otherwise both _load() the same "before" state and the second _save()
# would silently overwrite the first's vote.
_vote_lock = threading.Lock()


def _defaults() -> dict:
    return {"voting_open": True, "results_published": False, "votes": {}}


def _load() -> dict:
    if not VOTES_PATH.exists():
        return _defaults()
    try:
        with open(VOTES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _defaults()
    data.setdefault("voting_open", True)
    data.setdefault("results_published", False)
    data.setdefault("votes", {})
    return data


def _save(data: dict):
    VOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VOTES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Backgrounded, not inline - see weekly_score_service._save() for why a
    # blocking R2 upload on every submission risks starving Render's 4
    # request threads if several members vote around the same time.
    threading.Thread(target=r2_service.upload_file, args=(VOTES_PATH,), daemon=True).start()


def get_candidates() -> list:
    """The current Top 20 from Club Rankings, alphabetical rather than rank
    order - shown that way on purpose so the ballot doesn't visually nudge
    members toward the committee's existing ranking while they pick their
    own Top 10 (per committee discussion). Still pulled live from Club
    Rankings rather than a hardcoded list, so it always matches the same
    Top 20 shown on /players/rankings."""
    top20 = get_rankings()["players"][:TOP_N]
    return sorted(top20, key=str.casefold)


def get_voter_names() -> list:
    """Full club roster - the same source that already feeds the site-wide
    Feedback 'Submitting as' dropdown (player_service.get_player_names)."""
    return get_player_names()


def get_state() -> dict:
    """{"voting_open": bool, "results_published": bool} - never exposes the
    raw votes dict."""
    data = _load()
    return {"voting_open": data["voting_open"], "results_published": data["results_published"]}


def get_existing_vote(member_name: str):
    """A member's previously submitted Top 10, or None if they haven't
    voted yet - used to prefill the form on resubmission."""
    return _load()["votes"].get(member_name, {}).get("rankings")


def get_progress() -> tuple:
    """(members who've voted, total club roster) for the 'X / Y voted'
    counter - Y is the full roster, not scoped to active/current-season
    members, matching the confirmed decision in the feature spec."""
    data = _load()
    return len(data["votes"]), len(get_voter_names())


def submit_vote(member_name: str, rankings: list) -> tuple:
    """Validates and stores/overwrites `member_name`'s Top 10. Returns
    (True, "") on success or (False, reason) on failure rather than
    raising, so the route can surface the real reason either way."""
    member_name = (member_name or "").strip()
    with _vote_lock:
        data = _load()
        if not data["voting_open"]:
            return False, "Voting is currently closed."
        if member_name not in get_voter_names():
            return False, "Unrecognised member."
        if not isinstance(rankings, list) or len(rankings) != PICK_N:
            return False, f"Pick exactly {PICK_N} players."
        if len(set(rankings)) != PICK_N:
            return False, "Duplicate player in your ranking."
        candidates = set(get_candidates())
        if not all(name in candidates for name in rankings):
            return False, "One or more picks aren't in the current Top 20."
        data["votes"][member_name] = {
            "rankings": rankings,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)
    return True, ""


def set_voting_open(open_: bool):
    with _vote_lock:
        data = _load()
        data["voting_open"] = bool(open_)
        _save(data)


def set_results_published(published: bool):
    with _vote_lock:
        data = _load()
        data["results_published"] = bool(published)
        _save(data)


def compute_rankings(votes: dict) -> list:
    """Pure function, no file I/O (easy to unit test/reuse elsewhere):
    Borda-scores every current Top-20 candidate from a
    {member_name: {"rankings": [...10 names]}} dict. Rank 1 on a ballot is
    worth 10 points down to rank 10 worth 1; a candidate absent from a
    given ballot gets 0 from it. Ties break on the vector of
    (#1-place votes, #2-place votes, ... #10-place votes), most descending,
    then name."""
    candidates = get_candidates()
    points = {name: 0 for name in candidates}
    place_counts = {name: [0] * PICK_N for name in candidates}
    for entry in votes.values():
        for idx, name in enumerate((entry.get("rankings") or [])[:PICK_N]):
            if name in points:
                points[name] += PICK_N - idx
                place_counts[name][idx] += 1

    def sort_key(name):
        return (-points[name], [-c for c in place_counts[name]], name)

    ordered = sorted(candidates, key=sort_key)
    return [
        {
            "rank": i + 1,
            "name": name,
            "points": points[name],
            "first_place_votes": place_counts[name][0],
        }
        for i, name in enumerate(ordered)
    ]


def get_leaderboard() -> list:
    """compute_rankings() over the currently stored votes."""
    return compute_rankings(_load()["votes"])
