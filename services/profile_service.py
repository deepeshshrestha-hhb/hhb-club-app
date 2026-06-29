"""
Player profile storage: data/player_profiles.json
Keyed by URL slug (full_name lowercased, spaces → hyphens).
Photos saved to data/profile_photos/<slug>.<ext>.
"""
import json
import os
import re
from pathlib import Path
from werkzeug.utils import secure_filename

from config import Config
from services import r2_service

PROFILES_PATH = Path(Config.DATA_DIR) / "player_profiles.json"
PHOTOS_DIR = Path(Config.DATA_DIR) / "profile_photos"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB


def name_to_slug(full_name: str) -> str:
    slug = full_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _load_all() -> dict:
    if not PROFILES_PATH.exists():
        return {}
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all(profiles: dict):
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(PROFILES_PATH)


def get_profile(slug: str) -> dict | None:
    return _load_all().get(slug)


def save_profile(full_name: str, data: dict, photo_file=None) -> tuple[bool, str]:
    """Save or overwrite a player profile. Returns (ok, error_message)."""
    slug = name_to_slug(full_name)
    profiles = _load_all()
    existing = profiles.get(slug, {})

    photo_filename = existing.get("photo_filename")

    if photo_file and photo_file.filename:
        # Validate extension
        ext = photo_file.filename.rsplit(".", 1)[-1].lower() if "." in photo_file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Invalid file type '.{ext}'. Allowed: jpg, jpeg, png, gif, webp."

        # Read bytes to check size
        photo_bytes = photo_file.read()
        if len(photo_bytes) > MAX_PHOTO_BYTES:
            mb = len(photo_bytes) / (1024 * 1024)
            return False, f"Photo is {mb:.1f} MB — maximum allowed is 10 MB."

        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        # Remove old photo if extension changed
        if photo_filename and photo_filename != f"{slug}.{ext}":
            old_path = PHOTOS_DIR / photo_filename
            if old_path.exists():
                old_path.unlink(missing_ok=True)

        photo_filename = f"{slug}.{ext}"
        photo_path = PHOTOS_DIR / photo_filename
        with open(photo_path, "wb") as f:
            f.write(photo_bytes)
        r2_service.upload_file(photo_path)

    profiles[slug] = {
        "full_name": full_name,
        "slug": slug,
        "fav_opponent": data.get("fav_opponent", ""),
        "fav_partner": data.get("fav_partner", ""),
        "fav_shot": data.get("fav_shot", ""),
        "day_job": data.get("day_job", ""),
        "year_joined": data.get("year_joined", ""),
        "photo_filename": photo_filename,
    }
    _save_all(profiles)
    return True, ""


def get_photo_path(photo_filename: str) -> Path | None:
    if not photo_filename:
        return None
    path = PHOTOS_DIR / photo_filename
    return path if path.exists() else None


def get_all_profile_slugs() -> set:
    return set(_load_all().keys())


def get_all_profiles() -> dict:
    """All saved profiles keyed by slug. Used by club analytics (e.g. tenure)."""
    return _load_all()


def delete_profile(slug: str) -> bool:
    """Delete a profile and its photo. Returns True if a profile existed."""
    profiles = _load_all()
    profile = profiles.pop(slug, None)
    if profile is None:
        return False
    # Remove photo file if present
    photo = profile.get("photo_filename")
    if photo:
        photo_path = PHOTOS_DIR / photo
        if photo_path.exists():
            photo_path.unlink(missing_ok=True)
    _save_all(profiles)
    return True
