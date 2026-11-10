"""
HHB Annual Dinner & Gala 2026 (Sat 5 Dec 2026, 5-9 pm): /annual-dinner

All state lives in one workbook, data/AnnualDinner2026.xlsx, with four sheets:
  Settings  - key/value rows (venue name/address/map link, attendance target)
  Roles     - volunteer roles: id, role, holder, sort
  RSVPs     - one row per member: attending Yes/No, guest counts by age band, notes
  Champions - admin overrides/extras for the "2026 Champions" section

Writes follow the lessons from Weekly Score Upload (see CLAUDE.md 2026-09-08):
a module lock around every read-modify-write (one gunicorn worker, 4 threads),
an atomic temp-file-then-replace save, and the R2 upload in a background
thread so a slow upload can never tie up request threads.
"""
import os
import threading
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

from config import Config
from services import r2_service
from services.spond_service import LOCAL_TZ

SITE_URL = "https://www.hhbclub.co.uk"

EVENT_TITLE = "HHB Annual Dinner & Gala 2026"
EVENT_START_ISO = "2026-12-05T17:00:00+00:00"  # 5 pm UK time (GMT in December)
EVENT_DATE_DISPLAY = "Saturday 5 December 2026"
EVENT_TIME_DISPLAY = "5:00 pm – 9:00 pm"
# Dashboard banner shows up to and including this date, then hides itself.
BANNER_LAST_DAY = date(2026, 12, 6)

DATA_PATH = Path(Config.DATA_DIR) / "AnnualDinner2026.xlsx"

MAX_PER_BAND = 10
BANDS = ("adults", "teens", "children")

DEFAULT_SETTINGS = {
    "venue_name": "",
    "venue_address": "",
    "venue_map_url": "",
    "target": 35,
}

DEFAULT_ROLES = [
    ("Host of the Night", "Rukhsar Ahmed"),
    ("Head of Entertainment", "Deepesh Shrestha"),
    ("Head of Catering", "Zaheer Abbas"),
    ("Head of Hall Arrangements on the Day", ""),
    ("Head of Sound & Lighting", "Rukhsar Ahmed"),
    ("Overall Project Manager", ""),
]

SHEETS = {
    "Settings": ["key", "value"],
    "Roles": ["id", "role", "holder", "sort"],
    "RSVPs": ["member", "attending", "adults", "teens", "children", "notes", "updated_at"],
    "Champions": ["event", "winners"],
}

_lock = threading.Lock()


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

def _default_data() -> dict:
    return {
        "settings": dict(DEFAULT_SETTINGS),
        "roles": [
            {"id": i + 1, "role": r, "holder": h, "sort": i + 1}
            for i, (r, h) in enumerate(DEFAULT_ROLES)
        ],
        "rsvps": {},
        "champions": [],
    }


def _rows(ws):
    it = ws.iter_rows(values_only=True)
    header = next(it, None)
    if not header:
        return []
    header = [str(h or "").strip() for h in header]
    out = []
    for row in it:
        if row is None or all(v in (None, "") for v in row):
            continue
        out.append({header[i]: row[i] for i in range(min(len(header), len(row)))})
    return out


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _load() -> dict:
    if not DATA_PATH.exists():
        return _default_data()
    try:
        wb = load_workbook(DATA_PATH)
    except Exception:
        return _default_data()

    data = _default_data()
    if "Settings" in wb.sheetnames:
        for r in _rows(wb["Settings"]):
            k = _s(r.get("key"))
            if k in DEFAULT_SETTINGS:
                data["settings"][k] = r.get("value") if r.get("value") is not None else ""
        data["settings"]["target"] = max(1, _int(data["settings"]["target"], 35))
        for k in ("venue_name", "venue_address", "venue_map_url"):
            data["settings"][k] = _s(data["settings"][k])
    if "Roles" in wb.sheetnames:
        data["roles"] = [
            {"id": _int(r.get("id")), "role": _s(r.get("role")),
             "holder": _s(r.get("holder")), "sort": _int(r.get("sort"))}
            for r in _rows(wb["Roles"]) if _s(r.get("role"))
        ]
    if "RSVPs" in wb.sheetnames:
        data["rsvps"] = {}
        for r in _rows(wb["RSVPs"]):
            m = _s(r.get("member"))
            if not m:
                continue
            data["rsvps"][m] = {
                "member": m,
                "attending": _s(r.get("attending")) == "Yes",
                "adults": _int(r.get("adults")),
                "teens": _int(r.get("teens")),
                "children": _int(r.get("children")),
                "notes": _s(r.get("notes")),
                "updated_at": _s(r.get("updated_at")),
            }
    if "Champions" in wb.sheetnames:
        data["champions"] = [
            {"event": _s(r.get("event")), "winners": _s(r.get("winners"))}
            for r in _rows(wb["Champions"]) if _s(r.get("event"))
        ]
    data["roles"].sort(key=lambda r: (r["sort"], r["id"]))
    return data


def _build_workbook(data: dict) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    for name, cols in SHEETS.items():
        ws = wb.create_sheet(name)
        ws.append(cols)
    for k in DEFAULT_SETTINGS:
        wb["Settings"].append([k, data["settings"].get(k, "")])
    for r in data["roles"]:
        wb["Roles"].append([r["id"], r["role"], r["holder"], r["sort"]])
    for m in sorted(data["rsvps"], key=str.casefold):
        r = data["rsvps"][m]
        wb["RSVPs"].append([m, "Yes" if r["attending"] else "No",
                            r["adults"], r["teens"], r["children"], r["notes"], r["updated_at"]])
    for c in data["champions"]:
        wb["Champions"].append([c["event"], c["winners"]])
    return wb


def _save(data: dict):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_PATH.with_name(DATA_PATH.stem + ".tmp.xlsx")
    _build_workbook(data).save(tmp)
    os.replace(tmp, DATA_PATH)
    threading.Thread(target=r2_service.upload_file, args=(DATA_PATH,), daemon=True).start()


def _now() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def _members() -> list:
    from services.player_service import get_player_names
    return get_player_names()


# --------------------------------------------------------------------------
# Champions (auto from the tournament archive, admin overrides on top)
# --------------------------------------------------------------------------

_champ_cache = {"key": None, "rows": []}


def _auto_champions() -> list:
    """2026 winners straight from the tournament scoresheets, cached on the
    files' mtimes (parsing three .xlsm files on every page load is slow)."""
    tdir = Path(Config.BASE_DIR) / "tournaments"
    files = [
        tdir / "HHB Annual Doubles Classic - 2026.xlsm",
        tdir / "HHB Annual Championships - 2026.xlsm",
        tdir / "HHB Annual Players League - 2026.xlsm",
    ]
    key = tuple(f.stat().st_mtime if f.exists() else 0 for f in files)
    if _champ_cache["key"] == key:
        return _champ_cache["rows"]

    rows = []
    try:
        from services.tournament_service import get_doubles_tournament
        d = get_doubles_tournament(2026) or {}
        w = (d.get("knockouts") or {}).get("winner")
        if w:
            rows.append({"event": "Annual Doubles Classic", "winners": w.replace("/", " / "), "note": ""})
    except Exception:
        pass
    try:
        from services.championship_service import get_championship
        ch = get_championship(2026) or {}
        for key_, label in (("pool_a", "Championships – Pool A"), ("pool_b", "Championships – Pool B")):
            w = ((ch.get(key_) or {}).get("knockouts") or {}).get("winner")
            if w:
                rows.append({"event": label, "winners": w, "note": ""})
    except Exception:
        pass
    try:
        from services.league_service import get_league
        lg = get_league(2026) or {}
        if lg.get("is_complete") and lg.get("winner"):
            rows.append({"event": "Annual Players League", "winners": lg["winner"], "note": ""})
        elif lg:
            end = lg.get("season_end") or ""
            note = f"Season finishes {end}" if end and end != "TBC" else "Season in progress"
            rows.append({"event": "Annual Players League", "winners": "", "note": note})
    except Exception:
        pass

    _champ_cache.update(key=key, rows=rows)
    return rows


def get_champions(data=None) -> list:
    """Auto rows, with any admin row of the same event name replacing it
    (a blank override hides that event); other admin rows are appended."""
    if data is None:
        with _lock:
            data = _load()
    overrides = {c["event"]: c for c in data["champions"]}
    out = []
    for row in _auto_champions():
        o = overrides.pop(row["event"], None)
        if o is None:
            out.append({**row, "source": "auto"})
        elif o["winners"]:
            out.append({"event": row["event"], "winners": o["winners"], "note": "", "source": "manual"})
    for c in data["champions"]:
        if c["event"] in overrides and c["winners"]:
            out.append({"event": c["event"], "winners": c["winners"], "note": "", "source": "manual"})
    return out


# --------------------------------------------------------------------------
# Public reads
# --------------------------------------------------------------------------

def _summary(data: dict) -> dict:
    yes = [r for r in data["rsvps"].values() if r["attending"]]
    no = [r for r in data["rsvps"].values() if not r["attending"]]
    members = len(yes)
    adults = members + sum(r["adults"] for r in yes)
    teens = sum(r["teens"] for r in yes)
    children = sum(r["children"] for r in yes)
    total = adults + teens + children
    target = data["settings"]["target"]
    return {
        "members_yes": members,
        "members_no": len(no),
        "adults": adults,
        "teens": teens,
        "children": children,
        "guests": total - members,
        "total": total,
        "target": target,
        "progress_pct": min(100, round(total * 100 / target)) if target else 0,
        "coming": sorted((r["member"] for r in yes), key=str.casefold),
    }


def get_state() -> dict:
    """Everything the public page needs - no per-person guest breakdowns."""
    with _lock:
        data = _load()
    return {
        "settings": data["settings"],
        "roles": data["roles"],
        "summary": _summary(data),
        "responded": sorted(data["rsvps"], key=str.casefold),
    }


def get_rsvp(member: str):
    with _lock:
        return _load()["rsvps"].get(member)


def get_banner() -> dict | None:
    """Data for the Dashboard banner, or None once the event has passed."""
    if datetime.now(LOCAL_TZ).date() > BANNER_LAST_DAY:
        return None
    with _lock:
        data = _load()
    return {"start_iso": EVENT_START_ISO, "total": _summary(data)["total"],
            "date": EVENT_DATE_DISPLAY, "time": EVENT_TIME_DISPLAY}


def get_admin_data() -> dict:
    with _lock:
        data = _load()
    rows = sorted(data["rsvps"].values(), key=lambda r: r["member"].casefold())
    return {"rsvps": rows, "champion_overrides": data["champions"]}


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

def save_rsvp(payload: dict):
    """Validate and upsert one member's RSVP. Returns (record, None) or (None, error)."""
    member = _s(payload.get("member"))
    if member not in _members():
        return None, "Please pick your name from the list."
    att = payload.get("attending")
    if att not in (True, False, "Yes", "No", "yes", "no"):
        return None, "Please say whether you're coming."
    attending = att in (True, "Yes", "yes")
    counts = {}
    for b in BANDS:
        raw = payload.get(b, 0) if attending else 0
        if isinstance(raw, bool):
            return None, "Guest numbers must be whole numbers."
        if isinstance(raw, str):
            raw = raw.strip() or "0"
            if not raw.isdigit():
                return None, "Guest numbers must be whole numbers."
            raw = int(raw)
        if not isinstance(raw, int) or not 0 <= raw <= MAX_PER_BAND:
            return None, f"Guest numbers must be between 0 and {MAX_PER_BAND}."
        counts[b] = raw
    notes = _s(payload.get("notes"))[:500] if attending else ""

    record = {"member": member, "attending": attending, **counts, "notes": notes, "updated_at": _now()}
    with _lock:
        data = _load()
        data["rsvps"][member] = record
        _save(data)
    return record, None


def delete_rsvp(member: str):
    with _lock:
        data = _load()
        if data["rsvps"].pop(member, None) is not None:
            _save(data)


def claim_role(role_id: int, member: str):
    """Public claim: only an open role, only by a real member."""
    member = _s(member)
    if member not in _members():
        return "Please pick your name from the list."
    with _lock:
        data = _load()
        role = next((r for r in data["roles"] if r["id"] == role_id), None)
        if role is None:
            return "That role no longer exists."
        if role["holder"]:
            return f"Sorry, {role['holder']} has already taken this role."
        role["holder"] = member
        _save(data)
    return None


def admin_set_holder(role_id: int, holder: str):
    holder = _s(holder)
    if holder and holder not in _members():
        return "Unknown member."
    with _lock:
        data = _load()
        for r in data["roles"]:
            if r["id"] == role_id:
                r["holder"] = holder
                _save(data)
                return None
    return "Role not found."


def admin_rename_role(role_id: int, name: str):
    name = _s(name)[:80]
    if not name:
        return "Role name can't be empty."
    with _lock:
        data = _load()
        for r in data["roles"]:
            if r["id"] == role_id:
                r["role"] = name
                _save(data)
                return None
    return "Role not found."


def admin_add_role(name: str):
    name = _s(name)[:80]
    if not name:
        return "Role name can't be empty."
    with _lock:
        data = _load()
        next_id = max((r["id"] for r in data["roles"]), default=0) + 1
        next_sort = max((r["sort"] for r in data["roles"]), default=0) + 1
        data["roles"].append({"id": next_id, "role": name, "holder": "", "sort": next_sort})
        _save(data)
    return None


def admin_remove_role(role_id: int):
    with _lock:
        data = _load()
        data["roles"] = [r for r in data["roles"] if r["id"] != role_id]
        _save(data)


def admin_save_settings(form: dict):
    target = _int(form.get("target"), 0)
    if not 1 <= target <= 1000:
        return "Target must be between 1 and 1000."
    map_url = _s(form.get("venue_map_url"))
    if map_url and not map_url.startswith(("https://", "http://")):
        return "Map link must start with https://"
    with _lock:
        data = _load()
        data["settings"].update(
            venue_name=_s(form.get("venue_name"))[:120],
            venue_address=_s(form.get("venue_address"))[:200],
            venue_map_url=map_url[:500],
            target=target,
        )
        _save(data)
    return None


def admin_set_champion(event: str, winners: str):
    event = _s(event)[:80]
    if not event:
        return "Event name can't be empty."
    with _lock:
        data = _load()
        data["champions"] = [c for c in data["champions"] if c["event"] != event]
        data["champions"].append({"event": event, "winners": _s(winners)[:120]})
        _save(data)
    return None


def admin_remove_champion_override(event: str):
    with _lock:
        data = _load()
        data["champions"] = [c for c in data["champions"] if c["event"] != _s(event)]
        _save(data)


def export_rows() -> list:
    rows = []
    for r in get_admin_data()["rsvps"]:
        rows.append({
            "Member": r["member"],
            "Attending": "Yes" if r["attending"] else "No",
            "Adult guests (20+)": r["adults"],
            "Teen guests (13-19)": r["teens"],
            "Child guests (0-12)": r["children"],
            "Party size": (1 + r["adults"] + r["teens"] + r["children"]) if r["attending"] else 0,
            "Notes": r["notes"],
            "Updated": r["updated_at"],
        })
    return rows
