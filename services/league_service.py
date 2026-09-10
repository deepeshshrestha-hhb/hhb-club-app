import csv
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from config import Config
from services import r2_service
from services import spond_service
from services.excel_service import load_workbook_normalized
from services.tournament_service import _clean, _fmt_date

TOURNAMENTS_DIR = Path(Config.BASE_DIR) / "tournaments"


def list_league_years():
    years = []
    if TOURNAMENTS_DIR.exists():
        for f in TOURNAMENTS_DIR.glob("HHB Annual Players League - *.xlsm"):
            try:
                years.append(int(f.stem.split("-")[-1].strip()))
            except ValueError:
                pass
    return sorted(years, reverse=True)


def get_league(year):
    path = TOURNAMENTS_DIR / f"HHB Annual Players League - {year}.xlsm"
    if not path.exists():
        return None

    wb = load_workbook_normalized(path, data_only=True)

    # Rules
    rules = []
    for row in range(2, 30):
        text = wb["PointRules"].cell(row, 2).value
        if text:
            rules.append(_clean(text))

    match_ws = wb[str(year)]

    # From the 2026 season, a "Court No." column was inserted at K, pushing the
    # "Difference" and standings columns one to the right. Detect it per-file
    # (rather than hardcoding a year) so older seasons' original layout still
    # parses correctly.
    has_court_col = "court no" in str(match_ws.cell(4, 11).value or "").lower()
    diff_col = 12 if has_court_col else 11
    rank_col = 20 if has_court_col else 19

    # Scheduled start/end from header row (R1C3, R1C7)
    scheduled_start_raw = match_ws.cell(1, 3).value
    scheduled_end_raw = match_ws.cell(1, 7).value

    # OFF dates from row 2: R2C1='OFF', dates at C2, C4, C6, ...
    off_dates = []
    if _clean(match_ws.cell(2, 1).value) == "OFF":
        col = 2
        while True:
            v = match_ws.cell(2, col).value
            if v is None:
                break
            if hasattr(v, "year"):
                off_dates.append(_fmt_date(v))
            col += 2

    # --- Matches ---
    matches = []
    min_date = None
    max_date = None

    for row in range(5, 700):
        date_val = match_ws.cell(row, 1).value
        no = match_ws.cell(row, 2).value
        if no is None or not hasattr(date_val, "year"):
            continue

        p1 = _clean(match_ws.cell(row, 3).value)
        p2 = _clean(match_ws.cell(row, 4).value)
        s1 = match_ws.cell(row, 5).value  # team 1 score
        p3 = _clean(match_ws.cell(row, 6).value)
        p4 = _clean(match_ws.cell(row, 7).value)
        s2 = match_ws.cell(row, 8).value  # team 2 score
        w1 = _clean(match_ws.cell(row, 9).value)
        w2 = _clean(match_ws.cell(row, 10).value)
        court_no_raw = match_ws.cell(row, 11).value if has_court_col else None
        diff = match_ws.cell(row, diff_col).value

        if s1 is None or s2 is None:
            continue

        if min_date is None or date_val < min_date:
            min_date = date_val
        if max_date is None or date_val > max_date:
            max_date = date_val

        is_deuce = int(s1) == 21 and int(s2) == 20 or int(s1) == 20 and int(s2) == 21

        if isinstance(court_no_raw, float) and court_no_raw.is_integer():
            court_no = str(int(court_no_raw))
        else:
            court_no = _clean(court_no_raw)

        matches.append({
            "no": no,
            "date": _fmt_date(date_val),
            # Matches tab shows this per row (32+ rows a Sunday) - the full
            # "06 Sep 2024" from _fmt_date() (shared with other tournament
            # pages, so not changed globally) was eating column width that
            # Team 1 needed; a season never spans a year boundary, so the
            # year adds nothing here. lstrip (not %-d/%#d) for the no-leading
            # -zero day, since strftime's no-pad flag isn't portable between
            # Linux (Render) and Windows (local dev).
            "date_short": date_val.strftime("%d-%b").lstrip("0"),
            "date_raw": date_val,
            "p1": p1, "p2": p2,
            "score1": int(s1),
            "p3": p3, "p4": p4,
            "score2": int(s2),
            "winner": f"{w1} & {w2}" if w1 and w2 else w1 or w2,
            "court_no": court_no,
            "diff": abs(int(diff)) if diff is not None else abs(int(s1) - int(s2)),
            "is_deuce": is_deuce,
            "players": f"{p1}|{p2}|{p3}|{p4}",
        })

    # League Rule 6: only one win with a specific partner counts per Sunday -
    # a winning pair's second (and any later) win on the same date must be
    # struck off: still shown in the Matches tab (so the double-report stays
    # visible) but excluded from every calculation below (standings,
    # analytics, Overall Stats). `matches` is already in row order, which is
    # chronological submission order for anything written by
    # write_weekly_scores() (see its docstring), so a forward scan correctly
    # flags the later occurrence(s) as struck off.
    seen_winning_pairs = set()
    for m in matches:
        margin = m["score1"] - m["score2"]
        winning_pair = frozenset({m["p1"], m["p2"]}) if margin > 0 else frozenset({m["p3"], m["p4"]})
        key = (m["date_raw"], winning_pair)
        m["is_struck_off"] = key in seen_winning_pairs
        seen_winning_pairs.add(key)

    counted_matches = [m for m in matches if not m["is_struck_off"]]

    # --- Standings ---
    # Rank/Name (T/U, or S/T pre-2026) is a static roster block that
    # write_weekly_scores() never resorts, and its Played/Won/Lost/Points
    # reflect every match written to the sheet - including ones now struck
    # off above. So every number here, not just rank, is computed directly
    # from `counted_matches`; the sheet's Rank/Name block is read only for
    # the season's player roster, so anyone with zero counted matches still
    # appears (e.g. at 0/0). Per League Rule 9: rank by Wins, then NPD (point
    # differential, computed here rather than trusted from the sheet's
    # Points-Against SUMIF, which is a formula and so reads back blank after
    # any openpyxl save - see the module docstring on write_weekly_scores),
    # then Win %.
    roster = []
    for row in range(3, 100):
        rank_cell = match_ws.cell(row, rank_col).value
        player = match_ws.cell(row, rank_col + 1).value
        if rank_cell is None or player is None or not isinstance(rank_cell, (int, float)):
            break
        roster.append(_clean(player))

    played = Counter()
    won = Counter()
    point_diff = defaultdict(int)
    for m in counted_matches:
        margin = m["score1"] - m["score2"]
        played[m["p1"]] += 1
        played[m["p2"]] += 1
        played[m["p3"]] += 1
        played[m["p4"]] += 1
        point_diff[m["p1"]] += margin
        point_diff[m["p2"]] += margin
        point_diff[m["p3"]] -= margin
        point_diff[m["p4"]] -= margin
        winner1, winner2 = (m["p1"], m["p2"]) if margin > 0 else (m["p3"], m["p4"])
        won[winner1] += 1
        won[winner2] += 1

    # Roster players with 0 counted matches (not yet played this season, or
    # only in the struck-off match above) are left out of standings entirely,
    # not just hidden in the template - keeps "#" a consecutive rank among
    # actual participants (no gaps), and keeps them out of anything else that
    # reads standings (top_players_courts, the champion/runner-up/third
    # lookups, HHB Score's per-season participation level in
    # player_stats_service.py).
    standings = []
    for p in roster:
        pl = played.get(p, 0)
        if pl == 0:
            continue
        w = won.get(p, 0)
        standings.append({
            "player": p,
            "wins": w,
            "played": pl,
            "losses": pl - w,
            "points": 100 + 15 * w,
            "win_pct": round(w / pl * 100) if pl else 0,
            "point_diff": point_diff.get(p, 0),
        })

    standings.sort(key=lambda s: (-s["wins"], -s["point_diff"], -s["win_pct"], s["player"].casefold()))
    for i, s in enumerate(standings, start=1):
        s["rank"] = i

    # --- Analytics --- (counted_matches - struck-off matches don't count)
    total = len(counted_matches)
    sundays = len({m["date_raw"] for m in counted_matches})
    deuce = [m for m in counted_matches if m["is_deuce"]]
    diffs = [m["diff"] for m in counted_matches if m["diff"] > 0]
    avg_diff = round(sum(diffs) / len(diffs), 1) if diffs else 0
    biggest = max(counted_matches, key=lambda m: m["diff"]) if counted_matches else None
    squeaky = [m for m in counted_matches if m["diff"] == 1]

    # --- Status ---
    today = date.today()
    if not matches:
        status = "not_started"
    elif scheduled_end_raw and hasattr(scheduled_end_raw, "date") and scheduled_end_raw.date() > today:
        status = "in_progress"
    elif max_date and max_date.date() > today:
        status = "in_progress"
    else:
        status = "complete"

    is_complete = status == "complete"

    # Resolve season dates: use actual match dates once the season is
    # complete, scheduled header dates otherwise. This used to key off
    # "any matches exist yet" instead of `is_complete`, so an in-progress
    # season showed its Season End as the date of its most recent match
    # (e.g. 6-Sep, the first Sunday played) instead of the real scheduled
    # end (e.g. 22-Nov) - correct only in hindsight, once the season is
    # actually over and the last match date and the true end coincide.
    if is_complete and min_date and max_date:
        season_start_disp = _fmt_date(min_date)
        season_end_disp = _fmt_date(max_date)
    else:
        season_start_disp = _fmt_date(scheduled_start_raw) if scheduled_start_raw else "TBC"
        season_end_disp = _fmt_date(scheduled_end_raw) if scheduled_end_raw else "TBC"

    # Score frequency
    score_counter = Counter()
    for m in counted_matches:
        hi, lo = max(m["score1"], m["score2"]), min(m["score1"], m["score2"])
        score_counter[(hi, lo)] += 1
    top_scores = [(f"{h}-{l}", c) for (h, l), c in score_counter.most_common(5)]

    # Max wins by individual on a single day — Top 3
    day_wins = defaultdict(int)  # (player, date) -> wins
    for m in counted_matches:
        for w in [m["p1"] if m["winner"] == f"{m['p1']} & {m['p2']}" else None,
                  m["p2"] if m["winner"] == f"{m['p1']} & {m['p2']}" else None,
                  m["p3"] if m["winner"] == f"{m['p3']} & {m['p4']}" else None,
                  m["p4"] if m["winner"] == f"{m['p3']} & {m['p4']}" else None]:
            if w:
                day_wins[(w, m["date"])] += 1
    top_day_wins = sorted(day_wins.items(), key=lambda x: -x[1])[:3]
    top_individual_day = [{"player": p, "date": d, "wins": w} for (p, d), w in top_day_wins]

    # Pair wins/losses across full season
    pair_wins = defaultdict(int)
    pair_losses = defaultdict(int)
    for m in counted_matches:
        pair1 = tuple(sorted([m["p1"], m["p2"]]))
        pair2 = tuple(sorted([m["p3"], m["p4"]]))
        winner_pair = tuple(sorted([w.strip() for w in m["winner"].split("&")])) if "&" in m["winner"] else None
        if winner_pair == pair1:
            pair_wins[pair1] += 1
            pair_losses[pair2] += 1
        elif winner_pair == pair2:
            pair_wins[pair2] += 1
            pair_losses[pair1] += 1

    all_pairs = set(list(pair_wins.keys()) + list(pair_losses.keys()))
    pair_records = []
    for pair in all_pairs:
        w = pair_wins.get(pair, 0)
        l = pair_losses.get(pair, 0)
        if w + l < 2:
            continue
        pair_records.append({
            "pair": f"{pair[0]} & {pair[1]}",
            "wins": w,
            "losses": l,
            "played": w + l,
            "undefeated": l == 0 and w >= 5,
            "win_pct": round(w / (w + l) * 100) if (w + l) else 0,
        })
    pair_records.sort(key=lambda x: (-x["wins"], x["losses"]))
    top_pairs = pair_records[:10]
    undefeated_pairs = [p for p in pair_records if p["undefeated"]]

    # Matches per Sunday
    by_date = defaultdict(int)
    for m in counted_matches:
        by_date[m["date_raw"]] += 1
    busiest = max(by_date.items(), key=lambda x: x[1]) if by_date else None

    # Player appearances (for filter dropdown)
    player_set = set()
    for m in matches:
        for p in [m["p1"], m["p2"], m["p3"], m["p4"]]:
            if p:
                player_set.add(p)
    all_players = sorted(player_set)

    # Court usage for the top 5 standings players (added 2026 season) — lets us
    # see whether stronger players are actually spending more time on the top
    # courts, per the rotation rules.
    has_court_data = any(m["court_no"] for m in counted_matches)
    court_columns = sorted(
        {m["court_no"] for m in counted_matches if m["court_no"]},
        key=lambda c: (0, int(c)) if c.isdigit() else (1, c),
    )
    top_players_courts = []
    if has_court_data:
        top_names = [s["player"] for s in standings[:5]]
        court_counts = {name: Counter() for name in top_names}
        for m in counted_matches:
            if not m["court_no"]:
                continue
            for p in (m["p1"], m["p2"], m["p3"], m["p4"]):
                if p in court_counts:
                    court_counts[p][m["court_no"]] += 1
        for name in top_names:
            counts = court_counts[name]
            top_players_courts.append({
                "player": name,
                "counts": {c: counts.get(c, 0) for c in court_columns},
                "total": sum(counts.values()),
            })

    analytics = {
        "total_matches": total,
        "total_sundays": sundays,
        "avg_per_sunday": round(total / sundays, 1) if sundays else 0,
        "deuce_count": len(deuce),
        "deuce_pct": round(len(deuce) / total * 100, 1) if total else 0,
        "avg_diff": avg_diff,
        "biggest_win": biggest,
        "squeaky_wins": len(squeaky),
        "top_scores": top_scores,
        "busiest_sunday": {"date": _fmt_date(busiest[0]), "matches": busiest[1]} if busiest else None,
        "top_individual_day": top_individual_day,
        "top_pairs": top_pairs,
        "undefeated_pairs": undefeated_pairs,
        "has_court_data": has_court_data,
        "court_columns": court_columns,
        "top_players_courts": top_players_courts,
    }

    return {
        "year": year,
        "title": f"HHB Annual Players League {year}",
        "season_start": season_start_disp,
        "season_end": season_end_disp,
        "status": status,
        "is_complete": is_complete,
        "off_dates": off_dates,
        "standings": standings,
        "winner": standings[0]["player"] if standings and is_complete else "",
        "runner_up": standings[1]["player"] if len(standings) > 1 and is_complete else "",
        "third": standings[2]["player"] if len(standings) > 2 and is_complete else "",
        "matches": matches,
        "all_players": all_players,
        "analytics": analytics,
        "rules": rules,
    }


def _live_players_playing(sessions, target_date, hour):
    """Sum confirmed counts from a live spond_service.get_weekly_sessions() list
    for events on target_date starting at the given hour. None if no matching
    event was found (so the template can show a dash instead of a misleading 0)."""
    total = None
    target_iso = target_date.isoformat()
    for s in sessions:
        if s["sort_date"] != target_iso or not s["start_time"].startswith(f"{hour:02d}:"):
            continue
        total = (total or 0) + s["confirmed"]
    return total


def _historical_players_playing(target_date, hour):
    """Distinct attendee count for target_date/hour from data/signups_history.csv
    (accepted RSVPs for past events, ~6 months retained). None if that date
    doesn't appear in the cache at all (too old, or never fetched) — distinct
    from a genuine 0 (event happened, nobody accepted for that hour)."""
    path = os.path.join(Config.DATA_DIR, "signups_history.csv")
    if not os.path.exists(path):
        return None
    names = set()
    date_seen = False
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                start = datetime.fromisoformat(row.get("start") or "")
            except ValueError:
                continue
            if start.date() != target_date:
                continue
            date_seen = True
            if start.hour != hour:
                continue
            name = (row.get("full_name") or "").strip()
            if name:
                names.add(name)
    return len(names) if date_seen else None


def get_overall_stats(year):
    """Per-week season stats mirroring the scoresheet's own "Overall Stats"
    sheet: Week/Date/Total Players Playing (9-10 & 10-11)/Total Games
    Recorded/Max Wins by a player. Off weeks (e.g. a school-holidays break,
    marked by a blank Week number in the sheet) are included as highlighted
    break rows instead of regular data rows.

    Week, Date, and (for past seasons) Total Players Playing are read straight
    from the sheet, since that's exactly what's already been manually tracked
    there for completed seasons. Total Games Recorded and Max Wins/Player are
    always computed fresh from the parsed matches list instead of trusting the
    sheet's own (often-blank) copy, so they can never drift from what the
    Matches/Analytics tabs on the same page show — verified against every week
    of the 2024 season's real data (11/11 weeks matched exactly). Total Players
    Playing is backfilled from Spond when the sheet cell is blank: live current
    sign-ups for a today-or-future Sunday, or the signups_history.csv cache for
    a past one (best-effort — that cache only retains ~6 months).
    """
    path = TOURNAMENTS_DIR / f"HHB Annual Players League - {year}.xlsm"
    if not path.exists():
        return None

    league = get_league(year)
    if not league:
        return None

    wb = load_workbook_normalized(path, data_only=True)
    stats_ws = wb["Overall Stats"]

    matches_by_date = defaultdict(list)
    for m in league["matches"]:
        if m.get("is_struck_off"):
            continue
        d = m["date_raw"].date() if hasattr(m["date_raw"], "date") else m["date_raw"]
        matches_by_date[d].append(m)

    today = date.today()
    rows = []
    need_live = False
    week_dates = []
    last_break_note = None
    for row in range(4, 60):
        week_no = stats_ws.cell(row, 1).value
        date_val = stats_ws.cell(row, 2).value
        if not hasattr(date_val, "year"):
            break  # end of the table
        d = date_val.date()
        if week_no is None:
            # An off week (e.g. a school-holidays break) — no week number, and
            # usually only the first row of the break carries the note text, so
            # reuse it for the rest of that same break block.
            note = _clean(stats_ws.cell(row, 3).value) or last_break_note or "Off week — no League play"
            last_break_note = note
            week_dates.append((row, None, d, note))
            continue
        last_break_note = None
        week_dates.append((row, week_no, d, None))
        if d >= today:
            need_live = True

    live_sessions = spond_service.get_weekly_sessions(weeks_ahead=16) if need_live else []

    for row, week_no, d, break_note in week_dates:
        if break_note is not None:
            rows.append({
                "week": None,
                "date": _fmt_date(d),
                "is_break": True,
                "note": break_note,
            })
            continue

        p9 = stats_ws.cell(row, 3).value
        p10 = stats_ws.cell(row, 4).value
        if p9 is None:
            p9 = _live_players_playing(live_sessions, d, 9) if d >= today else _historical_players_playing(d, 9)
        if p10 is None:
            p10 = _live_players_playing(live_sessions, d, 10) if d >= today else _historical_players_playing(d, 10)

        day_matches = matches_by_date.get(d, [])
        win_counts = Counter()
        for m in day_matches:
            pair1 = f"{m['p1']} & {m['p2']}"
            if m["winner"] == pair1:
                win_counts[m["p1"]] += 1
                win_counts[m["p2"]] += 1
            else:
                win_counts[m["p3"]] += 1
                win_counts[m["p4"]] += 1
        max_wins = max(win_counts.values()) if win_counts else 0
        max_players = sorted(p for p, c in win_counts.items() if c == max_wins) if win_counts else []

        rows.append({
            "week": int(week_no),
            "date": _fmt_date(d),
            "is_break": False,
            "players_9_10": p9,
            "players_10_11": p10,
            "total_games": len(day_matches),
            "max_wins": max_wins,
            "max_wins_player": " / ".join(max_players),
        })

    return rows


# --- Weekly Score Upload: writing into the live season's workbook ---------

def get_league_roster(year):
    """Canonical player names for year's league - the 'Name' column of its
    standings table (same block get_league() reads for the Final Standings).
    Used to resolve a Spond attendee's first name to the exact spelling the
    sheet's own formulas already key off (e.g. distinguishing 'Rahul J' from
    'Rahul B'), so scores written from the web form line up with players the
    standings columns already recognise."""
    path = TOURNAMENTS_DIR / f"HHB Annual Players League - {year}.xlsm"
    if not path.exists():
        return []
    wb = load_workbook_normalized(path, data_only=False, keep_vba=True)
    ws = wb[str(year)]
    has_court_col = "court no" in str(ws.cell(4, 11).value or "").lower()
    rank_col = 20 if has_court_col else 19

    roster = []
    for row in range(3, 100):
        rank = ws.cell(row, rank_col).value
        player = ws.cell(row, rank_col + 1).value
        if rank is None or player is None or not isinstance(rank, (int, float)):
            break
        p = _clean(player)
        if p:
            roster.append(p)
    return roster


def resolve_attendee_names(year, attendees):
    """Map Spond attendee {"first_name", "last_name"} dicts to this year's
    league roster names where possible (applying the same first-name ALIASES
    the rest of the site uses to join Spond identities to tournament sheets,
    e.g. Spond 'Yogeshwar' -> roster 'Yogi'), disambiguating shared first
    names (e.g. 'Rahul J' vs 'Rahul B') by last-name initial. Anyone not yet
    in the roster (a brand-new player) falls back to their plain Title-cased
    first name, so they can still be selected - add them to the sheet's
    roster block separately for their results to count toward standings.
    Returns a sorted, de-duplicated list of names."""
    # Local import: player_stats_service imports this module at load time, so
    # importing it back at module scope here would be circular.
    from services.player_stats_service import ALIASES
    reverse_aliases = {v: k for k, v in ALIASES.items() if k != v}

    roster_by_first = defaultdict(list)
    for name in get_league_roster(year):
        roster_by_first[name.split()[0].lower()].append(name)

    resolved = set()
    for a in attendees:
        first_lower = (a.get("first_name") or "").strip().lower()
        if not first_lower:
            continue
        key = reverse_aliases.get(first_lower, first_lower)
        candidates = roster_by_first.get(key, [])
        if len(candidates) == 1:
            resolved.add(candidates[0])
            continue
        if candidates:
            last_initial = (a.get("last_name") or "").strip()[:1].lower()
            narrowed = [
                c for c in candidates
                if len(c.split()) > 1 and c.split()[1][:1].lower() == last_initial
            ]
            for c in (narrowed or candidates):
                resolved.add(c)
            continue
        resolved.add((a.get("first_name") or "").strip().title())

    return sorted(resolved, key=str.casefold)


def write_weekly_scores(target_date, matches):
    """Write finalised Weekly Score Upload matches into target_date's year's
    league workbook, in the same row/column layout get_league() already reads
    (Date/No./Player 1-4/Score 1-2/Court No., plus the per-row
    Winner/Difference/Points helper columns and each roster player's
    Played/Won/Lost/Points/PF standings columns). Court No. is only written
    when the sheet has that column (has_court_col - the 2026+ template); it's
    silently skipped for an older template so this never errors on a year
    without it. Returns the number of matches written; raises ValueError if
    that year has no league workbook yet.

    Existing blank rows already pre-built for target_date (if the sheet was
    set up ahead of the season) are filled in first; any remaining matches
    are appended as new rows after the table's current last row.

    Every played row's Winner/Difference/Points and every roster player's
    standings are then recomputed and written as literal values, not just the
    rows this call touches - the WHOLE sheet, old rows included. That's
    because openpyxl never evaluates formulas: loading the workbook and saving
    it drops the *cached* result of every formula in the file (not only ones
    we edit), so leaving old rows' formulas alone would make them read back
    as blank via get_league() until a human next opens and re-saves the file
    in real Excel. The Rank/Name (T/U) columns are never touched here - the
    player roster and any end-of-season re-sort of standings by rank stay a
    separate, manual step, same as before this feature existed.

    Trade-off: every row this function writes keeps its correct numbers but
    loses its live Excel formula, so hand-editing that row's score in Excel
    afterwards won't auto-update its Winner/Difference/Points - copy the
    formula from an untouched row if that's ever needed again.
    """
    if not matches:
        return 0

    year = target_date.year
    path = TOURNAMENTS_DIR / f"HHB Annual Players League - {year}.xlsm"
    if not path.exists():
        raise ValueError(f"No league workbook found for {year} ({path.name}).")

    wb = load_workbook_normalized(path, data_only=False, keep_vba=True)
    ws = wb[str(year)]

    has_court_col = "court no" in str(ws.cell(4, 11).value or "").lower()
    diff_col = 12 if has_court_col else 11
    pts_col = diff_col + 3
    rank_col = 20 if has_court_col else 19

    # Locate the table's current extent, any blank slots already pre-built
    # for target_date, and the next match "No." (cumulative across the whole
    # season, never reset per week - matches the existing sheets' convention).
    # Assumes a contiguous table with no gaps in Date/No. (true of every
    # season sheet so far - each week's rows are always added back-to-back).
    last_row = 4
    max_no = 0
    open_slots = []
    for row in range(5, 691):
        no = ws.cell(row, 2).value
        date_val = ws.cell(row, 1).value
        if no is None or not hasattr(date_val, "year"):
            break
        last_row = row
        if isinstance(no, (int, float)):
            max_no = max(max_no, int(no))
        if date_val.date() == target_date and ws.cell(row, 3).value is None:
            open_slots.append(row)

    target_dt = datetime(target_date.year, target_date.month, target_date.day)

    for m in matches:
        if open_slots:
            row = open_slots.pop(0)
        else:
            row = last_row + 1
            if row > 690:
                raise ValueError(
                    "This league workbook is full (season row limit reached) - "
                    "contact the developer to extend it."
                )
            last_row = row
            max_no += 1
            ws.cell(row, 1).value = target_dt
            ws.cell(row, 2).value = max_no

        ws.cell(row, 3).value = m["p1"]
        ws.cell(row, 4).value = m["p2"]
        ws.cell(row, 5).value = m["score1"]
        ws.cell(row, 6).value = m["p3"]
        ws.cell(row, 7).value = m["p4"]
        ws.cell(row, 8).value = m["score2"]
        if has_court_col and m.get("court_no") is not None:
            ws.cell(row, 11).value = m["court_no"]

    # Recompute Winner/Difference/Points for every played row (old and new),
    # and tally each player's Played/Won/Points-For along the way.
    played = Counter()
    won = Counter()
    pf = Counter()
    for row in range(5, last_row + 1):
        c = ws.cell(row, 3).value
        d = ws.cell(row, 4).value
        e = ws.cell(row, 5).value
        f = ws.cell(row, 6).value
        g = ws.cell(row, 7).value
        h = ws.cell(row, 8).value
        if e is None or h is None:
            continue
        e_v, h_v = float(e), float(h)
        winner1, winner2 = (c, d) if e_v > h_v else (f, g)

        ws.cell(row, 9).value = winner1
        ws.cell(row, 10).value = winner2
        ws.cell(row, diff_col).value = e_v - h_v
        ws.cell(row, pts_col).value = 15

        for p in (c, d, f, g):
            if p:
                played[p] += 1
        if c:
            pf[c] += e_v
        if d:
            pf[d] += e_v
        if f:
            pf[f] += h_v
        if g:
            pf[g] += h_v
        if winner1:
            won[winner1] += 1
        if winner2:
            won[winner2] += 1

    for row in range(3, 100):
        rank = ws.cell(row, rank_col).value
        player = ws.cell(row, rank_col + 1).value
        if rank is None or player is None or not isinstance(rank, (int, float)):
            break
        p = _clean(player)
        pl = played.get(p, 0)
        w = won.get(p, 0)
        ws.cell(row, rank_col + 2).value = pl
        ws.cell(row, rank_col + 3).value = w
        ws.cell(row, rank_col + 4).value = pl - w
        ws.cell(row, rank_col + 5).value = 100 + 15 * w
        ws.cell(row, rank_col + 6).value = round(pf.get(p, 0), 2)

    # Belt-and-braces for anyone who later opens this file in real Excel: force
    # a full recalculation on open, so formula cells this function didn't
    # touch (e.g. on the Individual Stats / Issues - DAQs sheets) pick up
    # fresh values instead of showing blank from the cache loss described above.
    wb.calculation.fullCalcOnLoad = True

    wb.save(path)
    r2_service.upload_file(path)

    # Local import: player_stats_service imports league_service at load time.
    from services.player_stats_service import invalidate_cache
    invalidate_cache()

    return len(matches)
