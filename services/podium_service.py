import os
import re
from flask import current_app

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
