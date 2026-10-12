"""
November Group Holiday 2026: data/holiday_nov2026.json

A private, unlisted availability poll for a group of 9 families (not a club
feature - nothing on the site links to it; see routes/holiday_routes.py).
Each family says whether they can make each candidate weekend and how many
people would come, so the group can pick the weekend with the most people
(minimum MIN_PEOPLE on the same weekend for it to go ahead).

Storage follows vote_service.py's JSON pattern: one record per family keyed
by family name (resubmitting overwrites in place), a lock around every
read-modify-write, and a backgrounded R2 upload. data/ is already an R2
synced prefix, so the file is pulled back down on every startup.
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from config import Config
from services import r2_service
from services.spond_service import LOCAL_TZ

# ---- Config (edit here) ---------------------------------------------------

# Secret part of the unlisted URL: /holiday/nov-2026-<HOLIDAY_SLUG>. Changing
# it retires the old link immediately (any other slug 404s).
HOLIDAY_SLUG = "5nupatxwf"

# Absolute site URL for Open Graph tags. Hardcoded rather than built from the
# request, because requests reach Render via the Cloudflare Worker proxy and
# Flask would otherwise build hhb-club.onrender.com links.
SITE_URL = "https://www.hhbclub.co.uk"

WEEKENDS = [
    {
        "key": "wk1",
        "name": "Weekend A",
        "dates": "Fri 13 – Sun 15 November 2026",
        "nights": "Nights of Fri 13 & Sat 14",
        "short": "13–14 Nov",
        "label": "",
    },
    {
        "key": "wk2",
        "name": "Weekend B",
        "dates": "Fri 20 – Sun 22 November 2026",
        "nights": "Nights of Fri 20 & Sat 21",
        "short": "20–21 Nov",
        "label": "Original first choice",
    },
]

FAMILIES = [
    "Barun Lal and family",
    "Birendra Shrestha and family",
    "Deepak Subedi and family",
    "Deepesh Shrestha and family",
    "Kalyan Bhandari and family",
    "Keshav Bhattarai and family",
    "Keshav Dahal and family",
    "Pankaj Shah and family",
    "Ram Aryal and family",
]

MIN_PEOPLE = 15        # needed on the same weekend for the holiday to go ahead
MAX_PER_FAMILY = 15    # upper bound on "number of people" per family/weekend
NOTE_MAX = 200

# ---------------------------------------------------------------------------

DATA_PATH = Path(Config.DATA_DIR) / "holiday_nov2026.json"

# Same rationale as vote_service._vote_lock: one gunicorn worker, 4 threads,
# all sharing this file.
_lock = threading.Lock()


def _load() -> dict:
    if not DATA_PATH.exists():
        return {"responses": {}}
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"responses": {}}
    data.setdefault("responses", {})
    return data


def _save(data: dict):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(DATA_PATH)
    threading.Thread(target=r2_service.upload_file, args=(DATA_PATH,), daemon=True).start()


def _parse_available(value):
    if isinstance(value, bool):
        return value
    v = str(value or "").strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return None


def save_response(payload: dict):
    """Validate and upsert one family's response. Returns (record, None) on
    success or (None, error message)."""
    family = (payload.get("family") or "").strip()
    if family not in FAMILIES:
        return None, "Please select your family."

    record = {"family": family}
    for wk in WEEKENDS:
        key = wk["key"]
        available = _parse_available(payload.get(f"{key}_available"))
        if available is None:
            return None, f"Please say whether you can make {wk['name']}."
        if available:
            try:
                people = int(payload.get(f"{key}_people"))
            except (TypeError, ValueError):
                return None, f"Please enter the number of people for {wk['name']}."
            if not 1 <= people <= MAX_PER_FAMILY:
                return None, f"Number of people for {wk['name']} must be 1–{MAX_PER_FAMILY}."
        else:
            people = 0
        record[f"{key}_available"] = "yes" if available else "no"
        record[f"{key}_people"] = people

    note = " ".join((payload.get("note") or "").split())
    record["note"] = note[:NOTE_MAX]
    record["updated_at"] = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    with _lock:
        data = _load()
        data["responses"][family] = record
        _save(data)
    return record, None


def _display_time(iso_local: str) -> str:
    """'2026-10-12 14:05' -> '12 Oct, 14:05' (already UK time)."""
    try:
        dt = datetime.strptime(iso_local, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso_local or ""
    return f"{dt.day} {dt.strftime('%b, %H:%M')}"


def get_state() -> dict:
    """Everything the page needs: per-family rows (all 9, alphabetical) and
    per-weekend totals with the leading weekend."""
    with _lock:
        responses = _load()["responses"]

    rows = []
    for family in FAMILIES:
        r = responses.get(family)
        if r:
            r = {**r, "updated_display": _display_time(r.get("updated_at"))}
        rows.append({"family": family, "response": r})

    totals = []
    for wk in WEEKENDS:
        key = wk["key"]
        people = sum(r[f"{key}_people"] for r in responses.values()
                     if r.get(f"{key}_available") == "yes")
        families = sum(1 for r in responses.values() if r.get(f"{key}_available") == "yes")
        totals.append({
            **wk,
            "people": people,
            "families": families,
            "need": max(0, MIN_PEOPLE - people),
            "min_reached": people >= MIN_PEOPLE,
        })

    top = max(t["people"] for t in totals)
    leaders = [t["key"] for t in totals if t["people"] == top] if top > 0 else []
    for t in totals:
        t["leading"] = t["key"] in leaders and len(leaders) == 1
        t["tied"] = t["key"] in leaders and len(leaders) > 1

    return {
        "rows": rows,
        "totals": totals,
        "responded": sum(1 for f in FAMILIES if f in responses),
        "family_count": len(FAMILIES),
        "min_people": MIN_PEOPLE,
    }
