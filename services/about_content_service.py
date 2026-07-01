"""
About Us page editable copy: data/about_content.json

Stores the admin-editable body text for the About page's four sections. The
"When & Where We Play" section is structured (two weekly sessions with
day/time/venue/courts/capacity) rather than freeform, since that's what it
actually is; the other three are freeform paragraph text (blank line = new
paragraph, rendered with white-space: pre-line).
"""
import json
from pathlib import Path

from config import Config
from services import r2_service

ABOUT_CONTENT_PATH = Path(Config.DATA_DIR) / "about_content.json"

SECTION_TITLES = {
    "who_are_we": "Who Are We?",
    "when_where": "When & Where We Play",
    "our_community": "Our Community",
    "why_badminton": "Why Badminton?",
}
SECTION_ORDER = ["who_are_we", "when_where", "our_community", "why_badminton"]
PARAGRAPH_KEYS = ("who_are_we", "our_community", "why_badminton")

DEFAULT_PARAGRAPHS = {
    "who_are_we": (
        "We are the Haggis and Haleem Badminton Club — a friendly, social badminton club "
        "based in Newton Mearns, Glasgow. Our name is a nod to the wonderful mix of "
        "cultures that make up our club: the Scottish haggis and the South Asian haleem, two hearty "
        "dishes that bring people together, much like we do on the badminton court.\n\n"
        "With 40+ members drawn from India, Pakistan, Bangladesh, Nepal, Malaysia, and Scotland, our club "
        "is a vibrant, multicultural community united by a shared love of the game. Our members range "
        "in age from their early 40s to their 60s, and while the competitive spirit is always alive, "
        "the camaraderie off the court is just as important to us.\n\n"
        "We are also proud of our HHB Junior Members — the teenage children of our veteran "
        "members and the club's upcoming badminton superstars. They bring fresh energy to the courts and "
        "are very much part of the HHB family, learning the game alongside the generation that came before them."
    ),
    "our_community": (
        "We are proud of the diversity and warmth within our group. Whether you are a seasoned player "
        "or just looking to stay active and social, the spirit here is always welcoming. Banter, "
        "competitive doubles, post-game chai — it is all part of the HHB experience.\n\n"
        "We are more than just a badminton club — we are a community that has been playing, competing, "
        "and growing together for years, right here in the heart of Newton Mearns."
    ),
    "why_badminton": (
        "Badminton is one of the most rewarding racket sports for overall health and wellbeing. Research has shown "
        "that regular badminton players benefit from improved hand-eye coordination, enhanced cognitive function, "
        "and better brain development. The dynamic nature of the sport — with its rapid directional changes, quick "
        "decision-making, and strategic thinking — keeps both body and mind sharp, contributing to increased "
        "longevity and a healthier lifestyle.\n\n"
        "But beyond the physical benefits, badminton is deeply rooted in social connection. The doubles format — "
        "which we emphasise at HHB — creates natural partnerships and teamwork, fostering meaningful friendships "
        "and a sense of belonging. Studies show that this social aspect of sport is equally vital to health and "
        "wellbeing, reducing stress, combating isolation, and improving mental health. At HHB, we believe that the "
        "combination of vigorous physical activity, mental engagement, and genuine community is what makes "
        "badminton such a transformative experience."
    ),
}

DEFAULT_WHEN_WHERE = {
    "intro": "We run two weekly sessions, both focused on doubles badminton:",
    "sunday": {
        "title": "Sunday Sessions", "time": "9:00 am – 11:00 am",
        "venue": "Eastwood High School", "courts": "4 courts", "capacity": "20 players max",
    },
    "wednesday": {
        "title": "Wednesday Sessions", "time": "7:00 pm – 9:00 pm",
        "venue": "Parklands Country Club", "courts": "2 courts", "capacity": "10 players max",
    },
    "note": (
        "Sessions fill up quickly — sign-up is managed through the Spond app. "
        "Members will receive an invite via Spond for each session."
    ),
}


def _defaults() -> dict:
    data = {key: DEFAULT_PARAGRAPHS[key] for key in PARAGRAPH_KEYS}
    data["when_where"] = json.loads(json.dumps(DEFAULT_WHEN_WHERE))
    return data


def _load() -> dict:
    defaults = _defaults()
    if not ABOUT_CONTENT_PATH.exists():
        return defaults
    try:
        with open(ABOUT_CONTENT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return defaults
    for key, default_val in defaults.items():
        data.setdefault(key, default_val)
    return data


def _save(data: dict):
    ABOUT_CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ABOUT_CONTENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(ABOUT_CONTENT_PATH)


def get_about_content() -> dict:
    return _load()


def update_paragraph_section(key: str, text: str) -> bool:
    """Update one of the freeform paragraph sections. Returns False for an unknown key."""
    if key not in PARAGRAPH_KEYS:
        return False
    data = _load()
    data[key] = text.strip()
    _save(data)
    return True


def update_when_where(fields: dict):
    data = _load()
    when_where = data.setdefault("when_where", json.loads(json.dumps(DEFAULT_WHEN_WHERE)))
    when_where["intro"] = (fields.get("intro") or "").strip()
    when_where["note"] = (fields.get("note") or "").strip()
    for day in ("sunday", "wednesday"):
        session = when_where.setdefault(day, {})
        session["title"] = (fields.get(f"{day}_title") or "").strip()
        session["time"] = (fields.get(f"{day}_time") or "").strip()
        session["venue"] = (fields.get(f"{day}_venue") or "").strip()
        session["courts"] = (fields.get(f"{day}_courts") or "").strip()
        session["capacity"] = (fields.get(f"{day}_capacity") or "").strip()
    _save(data)
