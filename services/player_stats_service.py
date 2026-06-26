"""
Computes per-player tournament statistics and HHB Rating across all three
tournament types. Results are cached in-process after the first call.

Name matching strategy: tournament data uses first names only (or pair format
"Name1 / Name2"). We normalise these to lowercase and apply ALIASES to map
known nickname/spelling variations back to the Spond firstName.
"""
from services.tournament_service import list_doubles_tournament_years, get_doubles_tournament
from services.championship_service import list_championship_years, get_championship
from services.league_service import list_league_years, get_league

# Maps tournament first-name → Spond firstName (lowercase).
# Only entries that differ from the Spond name are listed here.
ALIASES = {
    "nawaz": "allah nawaz",  # Allah Nawaz Khan plays as "Nawaz" (Spond firstName is "Allah Nawaz")
    "yogi": "yogeshwar",     # Yogeshwar Chandelia plays as "Yogi"
    "tousif": "mohammad",    # Mohammad Tousif plays as "Tousif"
    "alty": "altamash",      # Altamash Pervez sometimes listed as "Alty"
    "ruksar": "rukhsar",     # Spelling variation of Rukhsar Ahmed
    "rahul j": "rahul",      # Rahul Jagdale (distinguishes from Rahul B)
    "usman": "usman",        # Usman – ex-member, won't match Spond but kept for completeness
}

# Points per best achievement in a season/year
DT_PTS = {   # Annual Doubles Classic
    "winner": 100, "runner_up": 75, "third": 56,
    "semi": 36, "knockout": 20, "group": 10,
}
CH_PTS = {   # Annual Championships (per pool appearance)
    "winner": 85, "runner_up": 64, "third": 38,
    "semi": 20, "group": 8,
}
LG_PTS = {   # Annual Players League
    "champion": 70, "runner_up": 56, "third": 42,
    "top5": 28, "top10": 18, "participated": 10,
}

_cache = None


def invalidate_cache():
    """Drop the in-process HHB Score cache so the next request recomputes from
    freshly downloaded files. Called by the admin refresh actions."""
    global _cache
    _cache = None


def _n(name):
    return (name or "").strip().lower()


def _canon(tournament_name):
    n = _n(tournament_name)
    return ALIASES.get(n, n)


def _fns(team_str):
    """'Deepesh / Purvaiz' → ['deepesh', 'purvaiz'] canonicalised."""
    if not team_str:
        return []
    return [_canon(p) for p in team_str.replace(" / ", "/").split("/") if p.strip()]


def _best_knockout_level(fn, knockouts):
    """Return the best knockout achievement string for a player."""
    k = knockouts or {}
    if fn in set(_fns(k.get("winner", ""))): return "winner"
    if fn in set(_fns(k.get("runner_up", ""))): return "runner_up"
    if fn in set(_fns(k.get("third", ""))): return "third"
    sf = set()
    for sf_m in (k.get("semifinals") or []):
        sf |= set(_fns(sf_m.get("team1", ""))) | set(_fns(sf_m.get("team2", "")))
    if fn in sf: return "semi"
    qf = set()
    for qf_m in (k.get("quarterfinals") or []):
        qf |= set(_fns(qf_m.get("team1", ""))) | set(_fns(qf_m.get("team2", "")))
    if fn in qf: return "knockout"
    return "group"


def get_all_player_stats():
    """Return cached dict: {spond_first_name_lower: stats_dict}."""
    global _cache
    if _cache is not None:
        return _cache

    raw = {}  # fn → {dt, ch, lg data}

    def _ensure(fn):
        if fn not in raw:
            raw[fn] = {"dt": {}, "ch": {}, "lg": {}}

    # ── Annual Doubles Classic ─────────────────────────────────────────────
    for year in list_doubles_tournament_years():
        t = get_doubles_tournament(year)
        if not t:
            continue
        participants = set()
        for group in (t.get("groups") or []):
            for match in (group.get("matches") or []):
                for tf in ["team1", "team2"]:
                    for fn in _fns(match.get(tf, "")):
                        participants.add(fn)
                        _ensure(fn)
        for fn in participants:
            raw[fn]["dt"][year] = "group"
        k = t.get("knockouts")
        if k:
            for fn in participants:
                raw[fn]["dt"][year] = _best_knockout_level(fn, k)

    # ── Annual Championships ─────────────────────────────────────────────────
    for year in list_championship_years():
        c = get_championship(year)
        if not c:
            continue
        for pool_key, pool_label in [("pool_a", "A"), ("pool_b", "B")]:
            pool = c.get(pool_key, {})
            participants = set()
            for match in (pool.get("matches") or []):
                for tf in ["team1", "team2"]:
                    for fn in _fns(match.get(tf, "")):
                        participants.add(fn)
                        _ensure(fn)
            k = pool.get("knockouts", {})
            for fn in participants:
                if year not in raw[fn]["ch"]:
                    raw[fn]["ch"][year] = []
                raw[fn]["ch"][year].append(_best_knockout_level(fn, k))

    # ── Annual Doubles League ────────────────────────────────────────────────
    for year in list_league_years():
        l = get_league(year)
        if not l or not l.get("is_complete"):
            continue
        for s in (l.get("standings") or []):
            fn = _canon(s["player"])
            _ensure(fn)
            rank = s["rank"]
            if rank == 1:       level = "champion"
            elif rank == 2:     level = "runner_up"
            elif rank == 3:     level = "third"
            elif rank <= 5:     level = "top5"
            elif rank <= 10:    level = "top10"
            else:               level = "participated"
            raw[fn]["lg"][year] = {"level": level, "rank": rank}

    CURRENT_YEARS = {2024, 2025, 2026}

    # ── Summarise ─────────────────────────────────────────────────────────────
    result = {}
    for fn, d in raw.items():
        dt_ach = d["dt"]   # {year: level}
        ch_ach = d["ch"]   # {year: [level_poolA, level_poolB]}
        lg_ach = d["lg"]   # {year: {level, rank}}

        # Wins / runner-ups / thirds
        def _count(ach_dict, key):
            if isinstance(ach_dict, dict):
                vals = list(ach_dict.values())
            else:
                vals = ach_dict
            count = 0
            for v in vals:
                if isinstance(v, list):
                    count += sum(1 for x in v if x == key)
                elif isinstance(v, dict):
                    count += 1 if v.get("level") == key else 0
                else:
                    count += 1 if v == key else 0
            return count

        dt_wins = _count(dt_ach, "winner")
        dt_ru   = _count(dt_ach, "runner_up")
        dt_3rd  = _count(dt_ach, "third")
        ch_wins = sum(v.count("winner") for v in ch_ach.values())
        ch_ru   = sum(v.count("runner_up") for v in ch_ach.values())
        ch_3rd  = sum(v.count("third") for v in ch_ach.values())
        lg_wins = _count(lg_ach, "champion")
        lg_ru   = _count(lg_ach, "runner_up")
        lg_3rd  = _count(lg_ach, "third")

        # HHB Score (Cumulative) — all years
        dt_pts = sum(DT_PTS.get(v, 0) for v in dt_ach.values())
        ch_pts = sum(CH_PTS.get(lv, 0) for vlist in ch_ach.values() for lv in vlist)
        lg_pts = sum(LG_PTS.get(v.get("level", "participated"), 0) for v in lg_ach.values())

        # HHB Score (Current) — last 3 calendar years only
        dt_pts_cur = sum(DT_PTS.get(v, 0) for yr, v in dt_ach.items() if yr in CURRENT_YEARS)
        ch_pts_cur = sum(
            CH_PTS.get(lv, 0)
            for yr, vlist in ch_ach.items() if yr in CURRENT_YEARS
            for lv in vlist
        )
        lg_pts_cur = sum(
            LG_PTS.get(v.get("level", "participated"), 0)
            for yr, v in lg_ach.items() if yr in CURRENT_YEARS
        )

        result[fn] = {
            "dt_count": len(dt_ach),
            "ch_count": len(ch_ach),
            "lg_count": len(lg_ach),
            "total_wins": dt_wins + ch_wins + lg_wins,
            "total_runner_ups": dt_ru + ch_ru + lg_ru,
            "total_thirds": dt_3rd + ch_3rd + lg_3rd,
            "hhb_score_cumulative": dt_pts + ch_pts + lg_pts,
            "hhb_score_current": dt_pts_cur + ch_pts_cur + lg_pts_cur,
        }

    _cache = result
    return result
