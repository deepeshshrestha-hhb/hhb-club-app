"""
Club Rankings: data/club_rankings.json

A manually-curated Top Players list, distinct from the automated HHB Score /
League-stats leaderboard already shown on the Players page. Position in the
"players" list IS the rank (1-indexed) - there is no separate rank field to
keep in sync. Admin-only until visible_to_public is turned on.
"""
import json
from pathlib import Path

from config import Config
from services import r2_service

RANKINGS_PATH = Path(Config.DATA_DIR) / "club_rankings.json"

# Seeded 2026-09-15 by the committee (see CLAUDE.md Decisions Log for context).
DEFAULT_PLAYERS = [
    "Atul Anand", "Ziad Karamat", "Santosh Krishnan", "Thomas Jose", "Rukhsar Ahmed",
    "Vivek Arora", "Yogeshwar Chandelia", "Sandip Biswas", "Zaheer Abbas", "Altamash Pervez",
    "Ken Lee", "Aahil Ahmed", "Deepesh Shrestha", "Rahul Jagdale", "Faiyaz Shaik",
    "Rafay Khan", "Shaan Suvarna", "Suraj Suvarna", "Shoaib Ahmad", "Waqas Syed",
    "Shiva Koteeswaran", "Samir Goyal", "Mehtab Malik", "Mohammad Tousif", "Jalal Miah",
    "Vasu Vikram", "Vishal Gupta", "Purvaiz Mohammed", "Allah Nawaz Khan", "Parvez Malik",
    "Deepak Tejwani", "Mansoor Rafeeq", "Sengole Gomez", "Asim Khan",
]

DISCLAIMER = (
    "This ranking is based 50% on Annual Players League performance over the last 3 years, "
    "and 50% on subjective review by the Committee based on current player capabilities. "
    "It is reviewed and updated twice a year — once in December around the Annual Dinner, "
    "and once in June after the completion of the Annual Doubles Classic."
)


def _defaults() -> dict:
    return {"visible_to_public": False, "players": list(DEFAULT_PLAYERS)}


def _load() -> dict:
    if not RANKINGS_PATH.exists():
        return _defaults()
    try:
        with open(RANKINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _defaults()
    data.setdefault("visible_to_public", False)
    data.setdefault("players", list(DEFAULT_PLAYERS))
    return data


def _save(data: dict):
    RANKINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RANKINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(RANKINGS_PATH)


def get_rankings() -> dict:
    """Returns {"visible_to_public": bool, "players": [name, ...]} - a
    player's rank is simply (index in "players") + 1."""
    return _load()


def is_visible_to_public() -> bool:
    return bool(_load().get("visible_to_public", False))


def set_visible_to_public(visible: bool):
    data = _load()
    data["visible_to_public"] = bool(visible)
    _save(data)


def add_player(name: str, position: int) -> bool:
    """Insert `name` into the rankings at 1-based `position` - everyone
    already at or below that position shifts down one. Returns False if the
    name is empty, already ranked, or the position is out of range
    (1..len(players)+1, i.e. anywhere from the top to straight after the
    current last place)."""
    name = (name or "").strip()
    if not name:
        return False
    data = _load()
    players = data["players"]
    if name in players:
        return False
    if position < 1 or position > len(players) + 1:
        return False
    players.insert(position - 1, name)
    _save(data)
    return True


def move_player(name: str, direction: str) -> bool:
    """Swap `name` with its neighbour one place up ('up') or down ('down').
    Returns False if the player isn't in the list, an unknown direction was
    given, or the player is already at that end (nothing to do)."""
    data = _load()
    players = data["players"]
    if name not in players:
        return False
    idx = players.index(name)
    if direction == "up" and idx > 0:
        players[idx - 1], players[idx] = players[idx], players[idx - 1]
    elif direction == "down" and idx < len(players) - 1:
        players[idx + 1], players[idx] = players[idx], players[idx + 1]
    else:
        return False
    _save(data)
    return True
