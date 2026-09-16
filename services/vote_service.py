"""
Player Ranking Vote: data/player_votes.json

Lets club members vote on their own Top 10 (ranked) from the club's current
Top 20 (per Club Rankings), identity confirmed via a name dropdown - no
login. One vote per member, overwritten in place on resubmission. Storage
follows weekly_score_service.py's JSON pattern (lock-guarded read-modify-
write, backgrounded R2 upload) rather than an Excel workbook - the closest
Excel precedent, Feedback.xlsx, is append-only and has no clean way to
overwrite-by-submitter or hold admin flags alongside the rows.

Since there's no login, picking a name from the dropdown alone isn't enough
to prove identity - anyone could otherwise view or overwrite someone else's
ballot. Each member's first submission generates a 4-digit PIN, shown to
them once; viewing or changing that ballot afterwards requires it. Only the
PIN's hash is stored (never the plaintext, so it can't be read back from
the data file - not that this is a high-value target, but it costs nothing
extra given hmac.compare_digest is already the pattern admin login uses).
Admins bypass this entirely via a separate read-only "all ballots" view
(see routes/vote_routes.py) and can clear a member's vote outright if they
forget their PIN or want to redo it - clearing is the only recovery path,
there's no "resend the PIN" since it was never stored anywhere to resend.

See routes/vote_routes.py for the /vote and /vote/results pages.
"""
import hashlib
import hmac
import json
import secrets
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
PIN_LENGTH = 4

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


def _hash_pin(pin: str) -> str:
    return hashlib.sha256((pin or "").strip().encode("utf-8")).hexdigest()


def _generate_pin() -> str:
    return f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"


def has_voted(member_name: str) -> bool:
    return member_name in _load()["votes"]


def verify_pin(member_name: str, pin: str) -> bool:
    entry = _load()["votes"].get(member_name)
    if not entry:
        return False
    return hmac.compare_digest(entry.get("pin_hash", ""), _hash_pin(pin))


def get_vote_with_pin(member_name: str, pin: str):
    """A member's Top 10 if `pin` matches their stored PIN, else None -
    the only way to read back an existing ballot (besides the admin-only
    all-ballots view), so picking a name from the dropdown alone can't
    leak what someone else voted."""
    if not verify_pin(member_name, pin):
        return None
    return _load()["votes"][member_name]["rankings"]


def get_progress() -> tuple:
    """(members who've voted, total club roster) for the 'X / Y voted'
    counter - Y is the full roster, not scoped to active/current-season
    members, matching the confirmed decision in the feature spec."""
    data = _load()
    return len(data["votes"]), len(get_voter_names())


def submit_vote(member_name: str, rankings: list, pin: str = None) -> tuple:
    """Validates and stores/overwrites `member_name`'s Top 10. On a first
    submission this generates a new PIN and returns it (plaintext, the one
    and only time it's ever available - only its hash gets stored); on a
    resubmission the caller must supply the PIN that was shown the first
    time, checked against that stored hash, and the same PIN carries over
    unchanged (never regenerated, so one PIN covers every future edit).

    Returns (True, "", new_pin_or_None) on success, (False, reason, None)
    on failure - never raises, so the route can surface the real reason."""
    member_name = (member_name or "").strip()
    with _vote_lock:
        data = _load()
        if not data["voting_open"]:
            return False, "Voting is currently closed.", None
        if member_name not in get_voter_names():
            return False, "Unrecognised member.", None
        if not isinstance(rankings, list) or len(rankings) != PICK_N:
            return False, f"Pick exactly {PICK_N} players.", None
        if len(set(rankings)) != PICK_N:
            return False, "Duplicate player in your ranking.", None
        candidates = set(get_candidates())
        if not all(name in candidates for name in rankings):
            return False, "One or more picks aren't in the current Top 20.", None

        existing = data["votes"].get(member_name)
        new_pin = None
        if existing:
            if not hmac.compare_digest(existing.get("pin_hash", ""), _hash_pin(pin)):
                return False, "Incorrect PIN.", None
            pin_hash = existing["pin_hash"]
        else:
            new_pin = _generate_pin()
            pin_hash = _hash_pin(new_pin)

        data["votes"][member_name] = {
            "rankings": rankings,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "pin_hash": pin_hash,
        }
        _save(data)
    return True, "", new_pin


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
    """Borda-scores every current Top-20 candidate from a
    {member_name: {"rankings": [...10 names]}} dict. Rank 1 on a ballot is
    worth 10 points down to rank 10 worth 1; a candidate absent from a
    given ballot gets 0 from it (this is expected to happen a lot - members
    pick 10 of 20, so several candidates can end up with zero votes at all).
    Ties break, in order: the vector of (#1-place votes, #2-place votes,
    ... #10-place votes) most descending, then each candidate's *existing*
    position on /players/rankings (lower/better position wins) - not
    alphabetically. That committee-set order is exactly what this vote is
    meant to refine, so it's the fairer fallback for anyone the vote itself
    can't separate, rather than an arbitrary A-Z split among e.g. five
    candidates nobody picked at all."""
    candidates = get_candidates()
    rank_order = get_rankings()["players"][:TOP_N]
    original_rank = {name: i for i, name in enumerate(rank_order)}
    points = {name: 0 for name in candidates}
    place_counts = {name: [0] * PICK_N for name in candidates}
    for entry in votes.values():
        for idx, name in enumerate((entry.get("rankings") or [])[:PICK_N]):
            if name in points:
                points[name] += PICK_N - idx
                place_counts[name][idx] += 1

    def sort_key(name):
        return (-points[name], [-c for c in place_counts[name]], original_rank.get(name, len(rank_order)))

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


def admin_get_all_votes() -> list:
    """Every submitted ballot, alphabetical by member - the admin-only
    read path that bypasses PINs entirely (see module docstring). Never
    includes pin_hash."""
    data = _load()
    return [
        {"member_name": name, "rankings": entry["rankings"], "submitted_at": entry["submitted_at"]}
        for name, entry in sorted(data["votes"].items(), key=lambda kv: kv[0].casefold())
    ]


def admin_clear_vote(member_name: str) -> bool:
    """Deletes a member's ballot (and its PIN) so they can vote fresh - the
    only recovery path if they forget their PIN, since it was never stored
    anywhere retrievable. Returns False if they hadn't voted."""
    member_name = (member_name or "").strip()
    with _vote_lock:
        data = _load()
        if member_name not in data["votes"]:
            return False
        del data["votes"][member_name]
        _save(data)
    return True
