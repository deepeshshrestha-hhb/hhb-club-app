import os
import re
from pathlib import Path
from flask import current_app
from services import r2_service

PODIUM_DIR = os.path.join("static", "images", "podium")
_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Matches "key_1", "key_2" numbered variants
_NUMBERED = re.compile(r"^(.+)_(\d+)$")


def _scan() -> dict:
    """Return {base_key: [sorted list of (n, filename)]} for every photo in podium/."""
    try:
        folder = os.path.join(current_app.root_path, PODIUM_DIR)
        if not os.path.isdir(folder):
            return {}
        result: dict[str, list] = {}
        for fname in os.listdir(folder):
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in _EXTS:
                continue
            m = _NUMBERED.match(stem)
            if m:
                base, n = m.group(1), int(m.group(2))
            else:
                base, n = stem, 0
            result.setdefault(base, []).append((n, fname))
        for key in result:
            result[key].sort()
        return result
    except Exception:
        return {}


def get_podium_photos() -> set:
    """Return the set of base keys that have at least one photo."""
    return set(_scan().keys())


def get_podium_photo_urls(key: str) -> list:
    """Return ordered list of static URLs for all photos under a given key."""
    data = _scan()
    entries = data.get(key, [])
    return [f"/static/images/podium/{fname}" for _, fname in entries]


def get_podium_photo_pipe(key: str) -> str:
    """Return photo URLs as a pipe-separated string, safe for use in HTML attributes."""
    return "|".join(get_podium_photo_urls(key))


def get_podium_photo_list(key: str) -> list:
    """Return list of dicts with 'filename' and 'url' for admin management UI."""
    data = _scan()
    entries = data.get(key, [])
    return [
        {"filename": fname, "url": f"/static/images/podium/{fname}"}
        for _, fname in entries
    ]


def save_podium_photos(key: str, file_storages: list) -> list:
    """Save one or more uploaded FileStorage objects under the given key.

    New files are always stored with a numeric suffix (_1, _2, …) starting
    from the next available number. Returns list of saved filenames.
    """
    folder = Path(current_app.root_path) / PODIUM_DIR
    folder.mkdir(parents=True, exist_ok=True)

    existing = _scan().get(key, [])
    next_n = max((n for n, _ in existing), default=0) + 1

    saved = []
    for fs in file_storages:
        if not fs or not fs.filename:
            continue
        ext = Path(fs.filename).suffix.lower()
        if ext not in _EXTS:
            continue
        fname = f"{key}_{next_n}{ext}"
        local_path = folder / fname
        fs.save(str(local_path))
        r2_service.upload_file(local_path)
        saved.append(fname)
        next_n += 1

    return saved


def delete_podium_photo(filename: str) -> bool:
    """Delete a single podium photo by filename. Returns True on success."""
    folder = Path(current_app.root_path) / PODIUM_DIR
    local_path = folder / Path(filename).name  # strip any path traversal
    if not local_path.exists():
        return False
    r2_service.delete_file(local_path)
    local_path.unlink()
    return True
