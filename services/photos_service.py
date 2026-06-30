"""
Club photo management service.

Generic club photos (type='generic') are displayed on the About page and the
dedicated /photos/gallery page in chronological order.

Event-specific photos (type='event') are linked from each tournament/event page
and displayed on /photos/event/<event_id>.

Metadata lives in data/Photos.xlsx; image files live in
static/images/photos/ (local cache) and are mirrored to R2 under the
'photos/' prefix.

Event ID conventions used by tournament routes:
    doubles_<year>          HHB Annual Doubles Classic
    championships_<year>    HHB Annual Championships
    league_<year>           HHB Annual Players League
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import current_app

from services.excel_service import load_excel, save_excel
from services import r2_service

PHOTOS_FILE = "Photos.xlsx"
PHOTOS_SUBDIR = Path("static") / "images" / "photos"
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

_COLUMNS = ["photo_id", "filename", "caption", "type", "event_id", "upload_date", "event_date"]


def _photos_dir() -> Path:
    return Path(current_app.root_path) / PHOTOS_SUBDIR


def _parse_event_date(raw) -> datetime | None:
    """Parse a stored event date string into a datetime, or None if blank/invalid."""
    s = str(raw or "").strip()
    if s in ("", "nan"):
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_upload(raw) -> datetime:
    """Parse an upload_date string; falls back to datetime.min so it always sorts."""
    s = str(raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.min


def _format_event_date(raw) -> str:
    """Format a stored ISO date (YYYY-MM-DD) as a friendly '4-Jul-2023'.

    Returns "" for blank/missing dates and leaves unparseable values untouched."""
    dt = _parse_event_date(raw)
    if dt is None:
        s = str(raw or "").strip()
        return "" if s in ("", "nan") else s
    return f"{dt.day}-{dt.strftime('%b-%Y')}"


def _decorate(records: list[dict]) -> list[dict]:
    """Add the public image URL and friendly date to each photo record."""
    for r in records:
        r["url"] = photo_url(r["filename"])
        r["event_date"] = _format_event_date(r["event_date"])
    return records


def _load() -> pd.DataFrame:
    df = load_excel(PHOTOS_FILE)
    if df.empty:
        return pd.DataFrame(columns=_COLUMNS)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    # pandas reads blank cells as float NaN; normalize to "" so optional fields
    # (caption, event_date) don't render as the literal string "nan" in templates.
    return df[_COLUMNS].fillna("")


def get_all_photos(type_filter: str | None = None) -> list[dict]:
    """Return all photo metadata rows, newest first. Optionally filter by type."""
    df = _load()
    if type_filter:
        df = df[df["type"] == type_filter]
    df = df.sort_values("upload_date", ascending=False)
    return _decorate(df.to_dict("records"))


def get_generic_photos() -> list[dict]:
    """Generic club photos, most recent first by the photo's own date.

    Sorts chronologically on event_date (newest first); photos without a date
    fall back to their upload time so they still appear."""
    df = _load()
    df = df[df["type"] == "generic"].copy()
    df["_sort"] = df.apply(
        lambda r: _parse_event_date(r["event_date"]) or _parse_upload(r["upload_date"]),
        axis=1,
    )
    df = df.sort_values("_sort", ascending=False).drop(columns="_sort")
    return _decorate(df.to_dict("records"))


def get_event_photos(event_id: str) -> list[dict]:
    df = _load()
    df = df[(df["type"] == "event") & (df["event_id"] == event_id)]
    df = df.sort_values("upload_date", ascending=False)
    return _decorate(df.to_dict("records"))


def has_event_photos(event_id: str) -> bool:
    df = _load()
    return bool(len(df[(df["type"] == "event") & (df["event_id"] == event_id)]))


def photo_url(filename: str) -> str:
    return f"/static/images/photos/{filename}"


def upload_photo(
    file_storage,
    caption: str,
    photo_type: str,
    event_id: str = "",
    event_date: str = "",
) -> dict | None:
    """Save an uploaded photo and record its metadata. Returns the row dict or None
    on invalid file type."""
    ext = Path(file_storage.filename).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        return None

    photo_id = str(uuid.uuid4())
    filename = f"{photo_id}{ext}"

    folder = _photos_dir()
    folder.mkdir(parents=True, exist_ok=True)
    local_path = folder / filename
    file_storage.save(str(local_path))
    r2_service.upload_file(local_path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "photo_id": photo_id,
        "filename": filename,
        "caption": caption or "",
        "type": photo_type,
        "event_id": event_id or "",
        "upload_date": now,
        "event_date": event_date or "",
    }

    df = _load()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_excel(df, PHOTOS_FILE)
    return row


def delete_photo(photo_id: str) -> bool:
    """Delete a photo by ID (removes file + metadata row). Returns True on success."""
    df = _load()
    mask = df["photo_id"] == photo_id
    if not mask.any():
        return False

    filename = str(df.loc[mask, "filename"].iloc[0])
    local_path = _photos_dir() / filename
    if local_path.exists():
        r2_service.delete_file(local_path)
        local_path.unlink()

    df = df[~mask].reset_index(drop=True)
    save_excel(df, PHOTOS_FILE)
    return True
