import csv
import datetime
import os

from config import Config
from services.player_stats_service import get_all_player_stats


def _parse_age(dob_str):
    if not dob_str:
        return None
    try:
        dob = datetime.date.fromisoformat(dob_str)
        # Reject obvious placeholder dates
        if dob.year < 1920 or dob.year > datetime.date.today().year:
            return None
        today = datetime.date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        return None


def _fmt_dob(dob_str):
    if not dob_str:
        return ""
    try:
        dob = datetime.date.fromisoformat(dob_str)
        if dob.year < 1920 or dob.year > datetime.date.today().year:
            return ""
        return dob.strftime("%d %b %Y")
    except ValueError:
        return ""


def get_all_players():
    csv_path = os.path.join(Config.DATA_DIR, "hhb_members.csv")
    if not os.path.exists(csv_path):
        return []

    all_stats = get_all_player_stats()
    empty_stats = {
        "dt_count": 0, "ch_count": 0, "lg_count": 0,
        "total_wins": 0, "total_runner_ups": 0, "total_thirds": 0,
        "hhb_score_cumulative": 0, "hhb_score_current": 0,
    }

    players = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn_key = row["first_name"].strip().lower()
            stats = all_stats.get(fn_key, empty_stats)
            players.append({
                "full_name": row["full_name"],
                "email": row["email"],
                "dob": _fmt_dob(row["dob"]),
                "age": _parse_age(row["dob"]),
                **stats,
            })

    players.sort(key=lambda p: -p["hhb_score_current"])
    for i, p in enumerate(players):
        p["rank"] = i + 1
    return players
