from pathlib import Path
from config import Config
from services.excel_service import load_workbook_normalized
from services.tournament_service import _clean, _fmt_date, _match_winner

TOURNAMENTS_DIR = Path(Config.BASE_DIR) / "tournaments"


def list_championship_years():
    years = []
    if TOURNAMENTS_DIR.exists():
        for f in TOURNAMENTS_DIR.glob("HHB Annual Championships - *.xlsm"):
            try:
                years.append(int(f.stem.split("-")[-1].strip()))
            except ValueError:
                pass
    return sorted(years, reverse=True)


def _parse_pool_group(ws, pool_name):
    matches = []
    row = 3
    while True:
        no = ws.cell(row, 1).value
        if no is None:
            break
        score1 = ws.cell(row, 4).value
        score2 = ws.cell(row, 6).value
        if score1 is not None and score2 is not None:
            matches.append({
                "no": no,
                "date": _fmt_date(ws.cell(row, 2).value),
                "team1": _clean(ws.cell(row, 3).value),
                "score1": score1,
                "team2": _clean(ws.cell(row, 5).value),
                "score2": score2,
                "winner": _clean(ws.cell(row, 7).value),
                "margin": ws.cell(row, 8).value,
            })
        row += 1

    standings = []
    for r in range(3, row):
        rank = ws.cell(r, 10).value
        team = ws.cell(r, 11).value
        if rank is None or team is None:
            continue
        standings.append({
            "rank": rank,
            "team": _clean(team),
            "played": ws.cell(r, 12).value,
            "won": ws.cell(r, 13).value,
            "lost": ws.cell(r, 14).value,
            "points": ws.cell(r, 15).value,
            "pf": ws.cell(r, 16).value,
            "pa": ws.cell(r, 17).value,
            "nsd": ws.cell(r, 18).value,
        })
    standings.sort(key=lambda t: (-(t["points"] or 0), -(t["nsd"] or 0)))
    return {"name": pool_name, "matches": matches, "standings": standings}


def _parse_pool_knockouts(ws):
    def sets(r, *cols):
        return [ws.cell(r, c).value for c in cols if ws.cell(r, c).value is not None]

    sf1_t1 = _clean(ws.cell(5, 8).value)
    sf1_t1_sets = sets(5, 10, 12, 14)
    sf1_t2 = _clean(ws.cell(11, 8).value)
    sf1_t2_sets = sets(11, 10, 12, 14)
    sf1_winner = _match_winner(sf1_t1, sf1_t1_sets, sf1_t2, sf1_t2_sets)

    sf2_t1 = _clean(ws.cell(17, 8).value)
    sf2_t1_sets = sets(17, 10, 12, 14)
    sf2_t2 = _clean(ws.cell(23, 8).value)
    sf2_t2_sets = sets(23, 10, 12, 14)
    sf2_winner = _match_winner(sf2_t1, sf2_t1_sets, sf2_t2, sf2_t2_sets)

    final_t1 = _clean(ws.cell(7, 16).value)
    final_t1_sets = sets(7, 18, 20, 22)
    final_t2 = _clean(ws.cell(19, 16).value)
    final_t2_sets = sets(19, 18, 20, 22)
    final_winner = _match_winner(final_t1, final_t1_sets, final_t2, final_t2_sets)

    winner = _clean(ws.cell(13, 24).value)
    runner_up = _clean(ws.cell(23, 24).value)
    third = _clean(ws.cell(32, 24).value)

    third_t1 = _clean(ws.cell(29, 16).value)
    third_t1_sets = sets(29, 18, 20, 22)
    third_t2 = _clean(ws.cell(36, 16).value)
    third_t2_sets = sets(36, 18, 20, 22)
    third_winner = _match_winner(third_t1, third_t1_sets, third_t2, third_t2_sets)

    return {
        "semifinals": [
            {"team1": sf1_t1, "team1_sets": sf1_t1_sets, "team2": sf1_t2, "team2_sets": sf1_t2_sets, "winner": sf1_winner},
            {"team1": sf2_t1, "team1_sets": sf2_t1_sets, "team2": sf2_t2, "team2_sets": sf2_t2_sets, "winner": sf2_winner},
        ],
        "final": {"team1": final_t1, "team1_sets": final_t1_sets, "team2": final_t2, "team2_sets": final_t2_sets, "winner": final_winner or winner},
        "third_place": {"team1": third_t1, "team1_sets": third_t1_sets, "team2": third_t2, "team2_sets": third_t2_sets, "winner": third_winner or third},
        "winner": winner or final_winner,
        "runner_up": runner_up,
        "third": third or third_winner,
    }


def _parse_dates_rules(ws):
    important_dates = []
    for row in range(4, 6):
        label = ws.cell(row, 2).value
        date_val = ws.cell(row, 4).value
        if label and hasattr(date_val, "strftime"):
            important_dates.append({"label": _clean(label), "date": _fmt_date(date_val)})

    import re
    rules = []
    for row in range(3, 20):
        rule = ws.cell(row, 7).value
        if rule:
            text = _clean(rule)
            # Strip leading "N. " numbering from spreadsheet cells
            text = re.sub(r"^\d+\.\s*", "", text)
            if text:
                rules.append(text)

    return important_dates, rules


def get_championship(year):
    path = TOURNAMENTS_DIR / f"HHB Annual Championships - {year}.xlsm"
    if not path.exists():
        return None

    wb = load_workbook_normalized(path, data_only=True)

    important_dates, rules = _parse_dates_rules(wb["Dates"])
    pool_a = _parse_pool_group(wb["Pool A"], "Pool A")
    pool_a["knockouts"] = _parse_pool_knockouts(wb["Pool A - Knockouts"])
    pool_b = _parse_pool_group(wb["Pool B"], "Pool B")
    pool_b["knockouts"] = _parse_pool_knockouts(wb["Pool B - Knockouts"])

    return {
        "year": year,
        "title": f"HHB Annual Championships {year}",
        "important_dates": important_dates,
        "rules": rules,
        "pool_a": pool_a,
        "pool_b": pool_b,
    }
