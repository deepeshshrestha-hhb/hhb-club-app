"""
Gather the facts for the weekly Annual Players League WhatsApp round-up.

Read-only: downloads the League workbooks from production R2 into a temp
folder (never uploads anything), then prints a JSON fact sheet comparing the
season before and after the chosen Sunday - standings movement, the day's
per-player records, milestones reached/upcoming, and any all-time records
that changed. Used by the `league-weekly-update` Claude skill
(.claude/skills/league-weekly-update/SKILL.md), which turns it into the
message.

Run from the project root:

    python scripts/league_weekly_update.py              # latest Sunday
    python scripts/league_weekly_update.py 2026-09-27   # a specific Sunday
    python scripts/league_weekly_update.py --local      # use local tournaments/

R2 credentials come from .env.r2 (see pull_r2.py) or, failing that, .env.
Without them it falls back to the local tournaments/ folder.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env.r2")
load_dotenv(PROJECT_ROOT / ".env")

from services import league_analytics_service as la  # noqa: E402
from services import league_service as ls  # noqa: E402
from services import r2_service  # noqa: E402

LEAGUE_PREFIX = "tournaments/HHB Annual Players League - "


def _fetch_workbooks(use_local):
    """Copy every League workbook into a temp dir; returns (dir, source)."""
    tmp = Path(tempfile.mkdtemp(prefix="league_update_"))
    if not use_local and r2_service.is_enabled():
        client = r2_service.get_client()
        bucket = os.environ["R2_BUCKET"] if "R2_BUCKET" in os.environ else r2_service._env("R2_BUCKET")
        resp = client.list_objects_v2(Bucket=bucket, Prefix=LEAGUE_PREFIX)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".xlsm"):
                client.download_file(bucket, key, str(tmp / Path(key).name))
        return tmp, "r2"
    for f in (PROJECT_ROOT / "tournaments").glob("HHB Annual Players League - *.xlsm"):
        shutil.copy(f, tmp / f.name)
    return tmp, "local"


def _standings(matches):
    """Mirror of get_league()'s standings maths over a match subset."""
    played, won, pd = Counter(), Counter(), defaultdict(int)
    for m in matches:
        if m["is_struck_off"]:
            continue
        margin = 0 if m["is_awarded"] else m["score1"] - m["score2"]
        for p in (m["p1"], m["p2"]):
            played[p] += 1
            pd[p] += margin
        for p in (m["p3"], m["p4"]):
            played[p] += 1
            pd[p] -= margin
        for p in ((m["p1"], m["p2"]) if ls._team1_won(m) else (m["p3"], m["p4"])):
            won[p] += 1
    rows = [{"player": p, "wins": won[p], "played": n, "losses": n - won[p],
             "win_pct": round(won[p] / n * 100), "point_diff": pd[p]}
            for p, n in played.items()]
    rows.sort(key=lambda s: (-s["wins"], -s["point_diff"], -s["win_pct"], s["player"].casefold()))
    for i, s in enumerate(rows, 1):
        s["rank"] = i
    return rows


def _all_time(year, cutoff=None):
    """All-time analytics, optionally pretending `year`'s season stops
    before `cutoff` (a datetime) - i.e. the picture before that Sunday."""
    real = ls.get_league

    def patched(y):
        league = real(y)
        if league and y == year and cutoff is not None:
            league = copy.copy(league)
            league["matches"] = [m for m in league["matches"] if m["date_raw"] < cutoff]
            league["standings"] = _standings(league["matches"])
        return league

    la.get_league = patched
    try:
        return la._compute(sorted(ls.list_league_years()))
    finally:
        la.get_league = real


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tmp, source = _fetch_workbooks("--local" in sys.argv)
    ls.TOURNAMENTS_DIR = tmp
    la.TOURNAMENTS_DIR = tmp
    try:
        years = sorted(ls.list_league_years())
        year = int(args[0][:4]) if args else years[-1]
        league = ls.get_league(year)
        dates = sorted({m["date_raw"] for m in league["matches"]})
        target = datetime.fromisoformat(args[0]) if args else dates[-1]
        if target not in dates:
            sys.exit(f"No matches recorded for {target:%d-%b-%Y}. Dates in {year}: "
                     + ", ".join(f"{d:%d-%b}" for d in dates))

        upto = [m for m in league["matches"] if m["date_raw"] <= target]
        before_matches = [m for m in upto if m["date_raw"] < target]
        week = [m for m in upto if m["date_raw"] == target and not m["is_struck_off"]]
        after_st = _standings(upto)
        before_st = _standings(before_matches)
        before_rank = {s["player"]: s["rank"] for s in before_st}
        for s in after_st:
            s["prev_rank"] = before_rank.get(s["player"])

        # The day itself
        day = defaultdict(lambda: {"wins": 0, "losses": 0, "point_diff": 0})
        results = []
        for m in week:
            t1, t2 = (m["p1"], m["p2"]), (m["p3"], m["p4"])
            t1won = ls._team1_won(m)
            win, lose = (t1, t2) if t1won else (t2, t1)
            margin = 0 if m["is_awarded"] else abs(m["score1"] - m["score2"])
            for p in win:
                day[p]["wins"] += 1
                day[p]["point_diff"] += margin
            for p in lose:
                day[p]["losses"] += 1
                day[p]["point_diff"] -= margin
            results.append({"win": "/".join(win), "lose": "/".join(lose),
                            "score": f"{max(m['score1'], m['score2'])}-{min(m['score1'], m['score2'])}",
                            "margin": margin, "court": m["court_no"], "awarded": m["is_awarded"]})
        day_rows = sorted(({"player": p, **v} for p, v in day.items()),
                          key=lambda r: (-r["wins"], r["losses"], -r["point_diff"]))

        # All-time tallies up to and including this Sunday, plus everyone who
        # had ever played before it (any season).
        prior = [(y, ls.get_league(y)) for y in years if y < year]
        history = la._collect_matches([(y, lg) for y, lg in prior if lg] + [(year, {"matches": upto})])
        seen_before, totals = set(), {"matches": Counter(), "wins": Counter()}
        for m in history:
            for p in m["win"] + m["lose"]:
                totals["matches"][p] += 1
                if m["date_raw"] < target:
                    seen_before.add(p)
            for p in m["win"]:
                totals["wins"][p] += 1
        week_players = {p for m in week for p in (m["p1"], m["p2"], m["p3"], m["p4"])}
        season_before = {s["player"] for s in before_st}

        is_latest = target == dates[-1]
        a_after = _all_time(year, None if is_latest else target.replace(hour=23, minute=59))
        a_before = _all_time(year, target)

        def _key(x):
            return (x["player"], x["kind"], x["target"])
        prev_reached = {_key(x) for x in a_before["reached_milestones"]}
        reached_now = [x for x in a_after["reached_milestones"] if _key(x) not in prev_reached]
        # players_at_or_above == 1 means this player is the first ever there.
        for x in reached_now:
            x["players_at_or_above"] = sum(1 for v in totals[x["kind"]].values() if v >= x["target"])

        # Changes to all-time record tables
        record_keys = ["top_played", "top_wins", "top_win_pct", "top_pairs_played", "top_pairs_wins", "most_wins_one_sunday",
                       "busiest_sunday", "unbeaten_pairs", "biggest_wins"]
        record_changes = {k: {"before": a_before[k], "after": a_after[k]}
                          for k in record_keys if a_before[k] != a_after[k]}

        weekly_counts = Counter(m["date_raw"] for m in upto if not m["is_struck_off"])
        out = {
            "source": source,
            "year": year,
            "date": f"{target:%d-%b-%Y}",
            "week_number": dates.index(target) + 1,
            "matches_by_week": {f"{d:%d-%b}": weekly_counts[d] for d in sorted(weekly_counts)},
            "season_total_matches": sum(weekly_counts.values()),
            "struck_off_today": sum(1 for m in upto if m["date_raw"] == target and m["is_struck_off"]),
            "players_today": len(week_players),
            "standings": after_st,
            "day_records": day_rows,
            "perfect_days": [r for r in day_rows if r["losses"] == 0 and r["wins"] >= 3],
            "biggest_wins_today": sorted(results, key=lambda r: -r["margin"])[:3],
            "deuce_today": sum(1 for m in week if m["is_deuce"]),
            "one_point_games_today": sum(1 for r in results if r["margin"] == 1),
            "courts_today": dict(Counter(str(m["court_no"]) for m in week)),
            "all_time_debuts": sorted(p for p in week_players if la._name(p) not in seen_before),
            "season_first_appearances": sorted(p for p in week_players if p not in season_before),
            "milestones_reached_today": reached_now,
            "upcoming_milestones": a_after["upcoming_milestones"],
            "club_milestone": a_after["club_milestone"],
            "season_milestone": a_after["season_milestone"],
            "all_time_totals": a_after["totals"],
            "all_time_top_wins": a_after["top_wins"],
            "all_time_top_played": a_after["top_played"],
            "all_time_record_changes": record_changes,
            "links": {
                "standings": f"https://hhbclub.co.uk/tournaments/league/{year}/Standings",
                "analytics": "https://hhbclub.co.uk/tournaments/league/analytics",
            },
        }
        print(json.dumps(out, indent=1, default=str))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
