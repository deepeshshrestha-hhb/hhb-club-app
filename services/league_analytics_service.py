"""
All-time Annual Players League analytics: /tournaments/league/analytics

Aggregates every season's counted matches (struck-off Rule 6 repeats
excluded, exactly as get_league() does for a single season) into one
cross-season view - totals, player/pair leaderboards, unbeaten/winless
pairs, records, rivalries and upcoming 50/100 milestones.

Pure computation over get_league() output - no new data source. The result
is cached in-process keyed by every league file's mtime, so it recomputes
automatically after a Weekly Score Upload submit or an R2 refresh rewrites
a workbook, without re-parsing four .xlsm files on every page view.
"""
from collections import Counter, defaultdict

from services.league_service import TOURNAMENTS_DIR, get_league, list_league_years
from services.tournament_service import _fmt_date

# League sheets record players by first name/nickname, and one player's
# spelling has drifted between seasons. Only merge names confirmed to be
# the same person - a wrong merge would inflate someone else's record.
NAME_MERGE = {
    "Rahul": "Rahul J",  # 2026 sheet uses plain "Rahul" - Rahul Jagdale, the only Rahul in the club
}

TOP_N = 5
MIN_PLAYER_MATCHES_FOR_PCT = 50   # Best Win % needs a meaningful sample
MIN_PAIR_MATCHES_FOR_PCT = 10
MIN_PAIR_MATCHES_FOR_STREAK_LISTS = 3  # unbeaten / winless pairs
MATCH_MILESTONE_STEP = 50
WIN_MILESTONE_STEP = 50
MATCH_MILESTONE_WINDOW = 15   # "about to reach" = within this many matches
WIN_MILESTONE_WINDOW = 10
CLUB_MILESTONE_STEP = 100

_cache = {"key": None, "data": None}


def _name(n):
    return NAME_MERGE.get(n, n)


def _pair_label(pair):
    return " & ".join(pair)


def _cache_key(years):
    key = []
    for y in years:
        path = TOURNAMENTS_DIR / f"HHB Annual Players League - {y}.xlsm"
        try:
            key.append((y, path.stat().st_mtime))
        except OSError:
            key.append((y, None))
    return tuple(key)


def _collect_matches(leagues):
    """Flatten every season's counted matches into one chronological list
    with an explicit winning/losing pair per match."""
    out = []
    for year, league in leagues:
        season = []
        for idx, m in enumerate(league["matches"]):
            if m["is_struck_off"]:
                continue
            t1 = (_name(m["p1"]), _name(m["p2"]))
            t2 = (_name(m["p3"]), _name(m["p4"]))
            if m["score1"] != m["score2"]:
                team1_won = m["score1"] > m["score2"]
            else:
                # Genuinely level score - trust the sheet's own
                # Winner columns rather than guessing from the margin.
                if m["winner"] == f"{m['p1']} & {m['p2']}":
                    team1_won = True
                elif m["winner"] == f"{m['p3']} & {m['p4']}":
                    team1_won = False
                else:
                    continue
            win, lose = (t1, t2) if team1_won else (t2, t1)
            season.append({
                "year": year,
                "date_raw": m["date_raw"],
                "date": m["date"],
                "idx": idx,
                "win": win,
                "lose": lose,
                "win_score": max(m["score1"], m["score2"]),
                "lose_score": min(m["score1"], m["score2"]),
                "diff": abs(m["score1"] - m["score2"]),
                "court_no": m.get("court_no"),
                "is_awarded": m.get("is_awarded", False),
            })
        # Sheet row order is submission order within a Sunday; sort by date
        # first so streaks follow real chronology even if rows were pasted
        # out of date order in an older sheet.
        season.sort(key=lambda x: (x["date_raw"], x["idx"]))
        out.extend(season)
    return out


def _next_milestone(value, step):
    return (value // step + 1) * step


def _longest_streak(matches, key_fn_win, key_fn_lose):
    """Longest run of consecutive wins per entity (player or pair), in
    chronological order across all seasons. Returns (entity, length, start, end)."""
    current = defaultdict(int)
    start = {}
    best = {}
    for m in matches:
        for e in key_fn_win(m):
            if current[e] == 0:
                start[e] = m
            current[e] += 1
            if current[e] > best.get(e, (0,))[0]:
                best[e] = (current[e], start[e], m)
        for e in key_fn_lose(m):
            current[e] = 0
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[1][2]["date_raw"]))
    return ranked


def get_all_time_analytics():
    years = sorted(list_league_years())
    key = _cache_key(years)
    if _cache["key"] == key and _cache["data"] is not None:
        return _cache["data"]
    data = _compute(years)
    _cache["key"] = key
    _cache["data"] = data
    return data


def _compute(years):
    leagues = [(y, get_league(y)) for y in years]
    leagues = [(y, l) for y, l in leagues if l]
    if not leagues:
        return None

    matches = _collect_matches(leagues)
    current_year = leagues[-1][0]
    current_league = leagues[-1][1]
    current_in_progress = current_league["status"] != "complete"

    # --- Per-player / per-pair tallies ---
    played = Counter()
    wins = Counter()
    pair_played = Counter()
    pair_wins = Counter()
    partners = defaultdict(set)
    seasons_by_player = defaultdict(set)
    opp_meetings = Counter()
    opp_wins = Counter()   # (winner_player, loser_player) -> wins
    day_wins = Counter()   # (player, date) -> wins
    by_date = Counter()
    score_counter = Counter()
    points_scored = 0
    current_played = Counter()
    current_wins = Counter()
    current_sundays = defaultdict(set)

    for m in matches:
        by_date[m["date_raw"]] += 1
        if not m["is_awarded"]:  # awarded 1-0 isn't a real scoreline
            score_counter[(m["win_score"], m["lose_score"])] += 1
            points_scored += m["win_score"] + m["lose_score"]
        wp = tuple(sorted(m["win"]))
        lp = tuple(sorted(m["lose"]))
        pair_played[wp] += 1
        pair_played[lp] += 1
        pair_wins[wp] += 1
        for team in (m["win"], m["lose"]):
            a, b = team
            partners[a].add(b)
            partners[b].add(a)
        for p in m["win"] + m["lose"]:
            played[p] += 1
            seasons_by_player[p].add(m["year"])
            if m["year"] == current_year:
                current_played[p] += 1
                current_sundays[p].add(m["date_raw"])
        for p in m["win"]:
            wins[p] += 1
            day_wins[(p, m["date"])] += 1
            if m["year"] == current_year:
                current_wins[p] += 1
        for w in m["win"]:
            for l in m["lose"]:
                opp_meetings[tuple(sorted((w, l)))] += 1
                opp_wins[(w, l)] += 1

    total = len(matches)
    sundays = len(by_date)
    players = sorted(played)

    def player_row(p):
        pl, w = played[p], wins[p]
        return {"player": p, "played": pl, "wins": w, "losses": pl - w,
                "win_pct": round(w / pl * 100) if pl else 0,
                "seasons": len(seasons_by_player[p])}

    def pair_row(pair):
        pl, w = pair_played[pair], pair_wins[pair]
        return {"pair": _pair_label(pair), "played": pl, "wins": w, "losses": pl - w,
                "win_pct": round(w / pl * 100) if pl else 0,
                "active": all(p in current_played for p in pair)}

    top_played = [player_row(p) for p in sorted(players, key=lambda p: (-played[p], -wins[p], p))[:TOP_N]]
    top_wins = [player_row(p) for p in sorted(players, key=lambda p: (-wins[p], played[p], p))[:TOP_N]]
    pct_pool = [p for p in players if played[p] >= MIN_PLAYER_MATCHES_FOR_PCT]
    top_win_pct = [player_row(p) for p in sorted(
        pct_pool, key=lambda p: (-wins[p] / played[p], -played[p], p))[:TOP_N]]

    pairs = list(pair_played)
    top_pairs_played = [pair_row(x) for x in sorted(pairs, key=lambda x: (-pair_played[x], -pair_wins[x], x))[:TOP_N]]
    top_pairs_wins = [pair_row(x) for x in sorted(pairs, key=lambda x: (-pair_wins[x], pair_played[x], x))[:TOP_N]]
    pair_pct_pool = [x for x in pairs if pair_played[x] >= MIN_PAIR_MATCHES_FOR_PCT]
    top_pairs_pct = [pair_row(x) for x in sorted(
        pair_pct_pool, key=lambda x: (-pair_wins[x] / pair_played[x], -pair_played[x], x))[:TOP_N]]

    unbeaten = sorted(
        (x for x in pairs if pair_wins[x] == pair_played[x] and pair_played[x] >= MIN_PAIR_MATCHES_FOR_STREAK_LISTS),
        key=lambda x: (-pair_played[x], x))
    winless = sorted(
        (x for x in pairs if pair_wins[x] == 0 and pair_played[x] >= MIN_PAIR_MATCHES_FOR_STREAK_LISTS),
        key=lambda x: (-pair_played[x], x))

    # --- Records ---
    biggest_wins = [{
        "date": m["date"], "win": _pair_label(m["win"]), "lose": _pair_label(m["lose"]),
        "score": f"{m['win_score']}–{m['lose_score']}", "diff": m["diff"],
    } for m in sorted(matches, key=lambda m: (-m["diff"], m["date_raw"]))[:3]]

    best_day = sorted(day_wins.items(), key=lambda kv: (-kv[1], kv[0][0]))[:3]
    most_wins_one_sunday = [{"player": p, "date": d, "wins": w} for (p, d), w in best_day]

    busiest = sorted(by_date.items(), key=lambda kv: (-kv[1], kv[0]))[:1]
    busiest_sunday = {"date": _fmt_date(busiest[0][0]), "matches": busiest[0][1]} if busiest else None

    player_streaks = _longest_streak(matches, lambda m: m["win"], lambda m: m["lose"])[:3]
    longest_player_streaks = [{
        "name": p, "length": n, "from": s["date"], "to": e["date"],
    } for p, (n, s, e) in player_streaks]
    pair_streaks = _longest_streak(
        matches, lambda m: [tuple(sorted(m["win"]))], lambda m: [tuple(sorted(m["lose"]))])[:3]
    longest_pair_streaks = [{
        "name": _pair_label(p), "length": n, "from": s["date"], "to": e["date"],
    } for p, (n, s, e) in pair_streaks]

    deuce = sum(c for (h, l), c in score_counter.items() if (h, l) == (21, 20))
    one_point = sum(1 for m in matches if m["diff"] == 1)
    common_scores = [{"score": f"{h}–{l}", "count": c} for (h, l), c in score_counter.most_common(3)]
    decided = [m["diff"] for m in matches if m["diff"] > 0]
    avg_margin = round(sum(decided) / len(decided), 1) if decided else 0

    rivalries = []
    for (a, b), n in opp_meetings.most_common(TOP_N):
        rivalries.append({"a": a, "b": b, "meetings": n,
                          "a_wins": opp_wins[(a, b)], "b_wins": opp_wins[(b, a)]})

    social = sorted(players, key=lambda p: (-len(partners[p]), p))[:TOP_N]
    most_partners = [{"player": p, "partners": len(partners[p])} for p in social]

    ever_present = sorted(p for p in players if len(seasons_by_player[p]) == len(leagues))

    # --- Per-season comparison ---
    seasons = []
    for y, league in leagues:
        season_matches = [m for m in matches if m["year"] == y]
        season_players = {p for m in season_matches for p in m["win"] + m["lose"]}
        season_sundays = len({m["date_raw"] for m in season_matches})
        season_decided = [m["diff"] for m in season_matches if m["diff"] > 0]
        seasons.append({
            "year": y,
            "status": league["status"],
            "matches": len(season_matches),
            "sundays": season_sundays,
            "players": len(season_players),
            "per_sunday": round(len(season_matches) / season_sundays, 1) if season_sundays else 0,
            "avg_margin": round(sum(season_decided) / len(season_decided), 1) if season_decided else 0,
            "champion": league["winner"],
            "leader": league["standings"][0]["player"] if league["standings"] else "",
        })

    # --- Milestones ---
    # Only players active in the current season can realistically reach
    # their next milestone, so that's who's listed. "Sundays away" uses the
    # player's own current-season rate per Sunday attended.
    upcoming = []
    reached = []
    active = set(current_played) if current_in_progress else set()
    for p in sorted(active):
        n_sundays = len(current_sundays[p]) or 1
        for kind, total_now, this_season, step, window in (
            ("matches", played[p], current_played[p], MATCH_MILESTONE_STEP, MATCH_MILESTONE_WINDOW),
            ("wins", wins[p], current_wins[p], WIN_MILESTONE_STEP, WIN_MILESTONE_WINDOW),
        ):
            target = _next_milestone(total_now, step)
            to_go = target - total_now
            if to_go <= window:
                rate = this_season / n_sundays
                upcoming.append({
                    "player": p, "kind": kind, "current": total_now, "target": target,
                    "to_go": to_go,
                    "sundays_away": max(1, round(to_go / rate)) if rate else None,
                })
            # Milestones crossed during the current season
            before = total_now - this_season
            for t in range(_next_milestone(before, step), total_now + 1, step):
                reached.append({"player": p, "kind": kind, "target": t})
    upcoming.sort(key=lambda x: (x["to_go"], -x["target"], x["player"]))
    reached.sort(key=lambda x: (-x["target"], x["player"]))

    club_target = _next_milestone(total, CLUB_MILESTONE_STEP)
    current_total = seasons[-1]["matches"] if seasons else 0
    current_rate = seasons[-1]["per_sunday"] if seasons else 0
    club_milestone = {
        "target": club_target,
        "to_go": club_target - total,
        "sundays_away": max(1, round((club_target - total) / current_rate))
        if current_in_progress and current_rate else None,
    }
    season_target = _next_milestone(current_total, 50)
    season_milestone = {
        "year": current_year,
        "target": season_target,
        "to_go": season_target - current_total,
    } if current_in_progress else None

    return {
        "years": [y for y, _ in leagues],
        "current_year": current_year,
        "current_in_progress": current_in_progress,
        "totals": {
            "matches": total,
            "sundays": sundays,
            "seasons": len(leagues),
            "players": len(players),
            "points": points_scored,
            "avg_per_sunday": round(total / sundays, 1) if sundays else 0,
            "avg_margin": avg_margin,
            "deuce": deuce,
            "deuce_pct": round(deuce / total * 100, 1) if total else 0,
            "one_point": one_point,
            "pairs": len(pairs),
        },
        "seasons": seasons,
        "top_played": top_played,
        "top_wins": top_wins,
        "top_win_pct": top_win_pct,
        "top_pairs_played": top_pairs_played,
        "top_pairs_wins": top_pairs_wins,
        "top_pairs_pct": top_pairs_pct,
        "unbeaten_pairs": [pair_row(x) for x in unbeaten],
        "winless_pairs": [pair_row(x) for x in winless],
        "biggest_wins": biggest_wins,
        "most_wins_one_sunday": most_wins_one_sunday,
        "busiest_sunday": busiest_sunday,
        "longest_player_streaks": longest_player_streaks,
        "longest_pair_streaks": longest_pair_streaks,
        "common_scores": common_scores,
        "rivalries": rivalries,
        "most_partners": most_partners,
        "ever_present": ever_present,
        "upcoming_milestones": upcoming,
        "reached_milestones": reached,
        "club_milestone": club_milestone,
        "season_milestone": season_milestone,
        "constants": {
            "min_player_pct": MIN_PLAYER_MATCHES_FOR_PCT,
            "min_pair_pct": MIN_PAIR_MATCHES_FOR_PCT,
            "min_pair_lists": MIN_PAIR_MATCHES_FOR_STREAK_LISTS,
        },
    }
