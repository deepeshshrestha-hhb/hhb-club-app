import csv
import datetime
import os

from config import Config
from services.player_stats_service import get_all_player_stats
from services.analytics_service import get_player_hours


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


def get_player_names():
    """Lightweight, alphabetically sorted list of member full names (no stats).

    Used to populate the feedback "submitting as" dropdown, which renders on every
    page, so this deliberately just reads the cached members CSV and skips the
    HHB Score computation that get_all_players() does."""
    csv_path = os.path.join(Config.DATA_DIR, "hhb_members.csv")
    if not os.path.exists(csv_path):
        return []
    names = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("full_name") or "").strip()
            if name:
                names.append(name)
    names.sort(key=str.casefold)
    return names


def get_all_players():
    csv_path = os.path.join(Config.DATA_DIR, "hhb_members.csv")
    if not os.path.exists(csv_path):
        return []

    all_stats = get_all_player_stats()
    empty_stats = {
        "dt_count": 0, "ch_count": 0, "lg_count": 0,
        "total_wins": 0, "total_runner_ups": 0, "total_thirds": 0,
        "hhb_score_cumulative": 0, "hhb_score_current": 0,
        "breakdown": {"doubles": [], "champ_a": [], "champ_b": [], "league": []},
    }

    hours = get_player_hours()
    empty_hours = {"hours_last_four_weeks": 0.0, "hours_last_six_months": 0.0}

    players = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn_key = row["first_name"].strip().lower()
            stats = all_stats.get(fn_key, empty_stats)
            player_hours = hours.get(row["full_name"], empty_hours)
            players.append({
                "full_name": row["full_name"],
                "email": row["email"],
                "dob": _fmt_dob(row["dob"]),
                "age": _parse_age(row["dob"]),
                **stats,
                **player_hours,
            })

    players.sort(key=lambda p: -p["hhb_score_current"])
    for i, p in enumerate(players):
        p["rank"] = i + 1
    return players
