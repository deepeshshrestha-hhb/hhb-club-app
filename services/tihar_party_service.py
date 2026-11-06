"""
Tihar Party RSVP (Sat 7 Nov 2026): data/tihar_party.json

A private headcount for a group of 9 families (not a club feature - nothing on
the site links to it; see routes/party_routes.py). Each family says how many of
them are coming; 0 means they can't make it.

Storage follows vote_service.py's JSON pattern: one record per family keyed by
family name (resubmitting overwrites in place), a lock around every
read-modify-write, and a backgrounded R2 upload. data/ is already an R2 synced
prefix, so the file is pulled back down on every startup.
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from config import Config
from services import r2_service
from services.spond_service import LOCAL_TZ

# Absolute site URL for Open Graph tags. Hardcoded rather than built from the
# request, because requests reach Render via the Cloudflare Worker proxy and
# Flask would otherwise build hhb-club.onrender.com links.
SITE_URL = "https://www.hhbclub.co.uk"

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

MAX_PER_FAMILY = 15

DATA_PATH = Path(Config.DATA_DIR) / "tihar_party.json"

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


def save_response(payload: dict):
    """Validate and upsert one family's headcount. Returns (record, None) on
    success or (None, error message)."""
    family = (payload.get("family") or "").strip()
    if family not in FAMILIES:
        return None, "Please select your family."
    try:
        people = int(payload.get("people"))
    except (TypeError, ValueError):
        return None, "Please enter how many of you are coming."
    if not 0 <= people <= MAX_PER_FAMILY:
        return None, f"Number of people must be 0–{MAX_PER_FAMILY}."

    record = {
        "family": family,
        "people": people,
        "updated_at": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
    }
    with _lock:
        data = _load()
        data["responses"][family] = record
        _save(data)
    return record, None


def get_state() -> dict:
    """Per-family rows (all 9, alphabetical) plus the running totals."""
    with _lock:
        responses = _load()["responses"]

    rows = [{"family": f, "response": responses.get(f)} for f in FAMILIES]
    answered = [responses[f] for f in FAMILIES if f in responses]
    return {
        "rows": rows,
        "total_people": sum(r["people"] for r in answered),
        "families_coming": sum(1 for r in answered if r["people"] > 0),
        "responded": len(answered),
        "family_count": len(FAMILIES),
    }
