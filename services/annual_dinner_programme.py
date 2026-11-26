"""Programme & menu for the HHB Annual Dinner & Gala 2026 (/annual-dinner/programme).

The one place to edit the running order and the menu. Each slot's time is
24-hour "HH:MM" UK time on the event day; the page shows it as "5:00 pm" and
uses it to mark the current slot as "Now" while the event is on.

highlight=True gives a slot the gold "key moment" accent. Keep "Surprise Game"
exactly as it is: no sub-line, icon or hint about what it is.
"""

EVENT_DAY = "2026-12-05"  # UK time; GMT in December, so no offset to worry about

SCHEDULE = [
    {"time": "17:00", "title": "Arrivals and snacks", "lead": "Zaheer", "mins": 45},
    {"time": "17:45", "title": "Welcome by host", "lead": "Rukhsar", "mins": 5},
    {"time": "17:50", "title": "HHB Club - 2026 round up",
     "sub": "Tournaments, website, annual holiday, annual picnic", "lead": "Deepesh", "mins": 10},
    {"time": "18:00", "title": "Song Performance 1", "lead": "Rukhsar", "mins": 5},
    {"time": "18:05", "title": "Awards ceremony", "lead": "Deepesh", "mins": 20, "highlight": True},
    {"time": "18:25", "title": "Under-12s game", "lead": "Deepesh", "mins": 15},
    {"time": "18:40", "title": "Song Performance 2", "lead": "Deepesh", "mins": 5},
    {"time": "18:45", "title": "Teens game", "lead": "Deepesh", "mins": 15},
    {"time": "19:00", "title": "Song Performance 3", "lead": "Zaheer", "mins": 5},
    {"time": "19:05", "title": "Family Fortunes (Top 10)", "lead": "Deepesh", "mins": 25},
    {"time": "19:30", "title": "Dinner served", "lead": "Zaheer", "mins": 45, "highlight": True},
    {"time": "20:15", "title": "Surprise Game", "lead": "Deepesh", "mins": 15, "highlight": True},
    {"time": "20:30", "title": "Dessert, music and mingling", "lead": "Everybody", "mins": 15},
    {"time": "20:45", "title": "Closing Thanks and Group Photos", "lead": "Rukhsar/Deepesh", "mins": 15},
    {"time": "21:00", "title": "Close", "end": True},
]

# (name, vegetarian)
MENU = [
    {"course": "Starters", "icon": "🥗", "items": [
        ("Chicken Roast", False), ("Dahi Bara", True), ("Aloo Tikki", True)]},
    {"course": "Mains", "icon": "🍛", "items": [
        ("Lamb Qorma", False), ("Chicken Pulao", False), ("Palak Paneer", True),
        ("Tadka Daal", True), ("Naan", True)]},
    {"course": "Desserts", "icon": "🍰", "items": [
        ("Kheer", True), ("Chocolate Cake", False), ("Vanilla Cake", False)]},
]


def _display_time(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{(h - 1) % 12 + 1}:{m:02d} {'am' if h < 12 else 'pm'}"


def get_schedule() -> list[dict]:
    """Slots with a display time and a UTC ISO start (for the "Now" marker)."""
    return [{**s, "display_time": _display_time(s["time"]),
             "start_iso": f"{EVENT_DAY}T{s['time']}:00+00:00"} for s in SCHEDULE]


def get_menu() -> list[dict]:
    return MENU
