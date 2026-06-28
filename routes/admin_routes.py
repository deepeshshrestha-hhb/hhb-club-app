import hmac
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
)

from config import Config
from services import r2_service
from services.spond_service import fetch_members_to_csv
from services.player_stats_service import invalidate_cache
from services.podium_service import get_podium_photo_list, save_podium_photos, delete_podium_photo
from services.photos_service import (
    get_all_photos,
    upload_photo,
    delete_photo as delete_club_photo,
)

admin_bp = Blueprint("admin", __name__)


def _credentials_configured():
    return bool(Config.ADMIN_USERNAME and Config.ADMIN_PASSWORD)


def _check_credentials(username, password):
    """Constant-time check against the configured admin credentials."""
    if not _credentials_configured():
        return False
    user_ok = hmac.compare_digest(username or "", Config.ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(password or "", Config.ADMIN_PASSWORD)
    return user_ok and pass_ok


def _safe_next(target):
    """Only allow same-site relative redirects (avoid open-redirect via ?next=)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _check_credentials(request.form.get("username"), request.form.get("password")):
            session["is_admin"] = True
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.admin_page"))
        flash("Invalid username or password.")
    return render_template("login.html")


@admin_bp.route("/admin/logout")
def logout():
    session.pop("is_admin", None)
    flash("Logged out.")
    return redirect(url_for("dashboard"))


@admin_bp.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")


@admin_bp.route("/admin/sync_spond", methods=["POST"])
@admin_required
def sync_spond_route():
    """Re-fetch the member list from Spond, rewrite the local CSV, and upload it
    to R2. Use after a player joins or leaves."""
    fetch_members_to_csv()
    invalidate_cache()
    flash("Spond member list refreshed.")
    return redirect(url_for("admin.admin_page"))


@admin_bp.route("/admin/podium/photos")
@admin_required
def podium_photos():
    """Return existing photos for a podium key as JSON."""
    key = request.args.get("key", "").strip()
    if not key:
        return jsonify({"error": "key required"}), 400
    return jsonify({"photos": get_podium_photo_list(key)})


@admin_bp.route("/admin/podium/upload", methods=["POST"])
@admin_required
def podium_upload():
    """Upload one or more photos for a podium key."""
    key = request.form.get("key", "").strip()
    if not key:
        return jsonify({"error": "key required"}), 400
    files = request.files.getlist("photos")
    if not files:
        return jsonify({"error": "no files"}), 400
    saved = save_podium_photos(key, files)
    return jsonify({"ok": True, "saved": saved, "photos": get_podium_photo_list(key)})


@admin_bp.route("/admin/podium/delete", methods=["POST"])
@admin_required
def podium_delete():
    """Delete a single podium photo by filename."""
    data = request.get_json(silent=True) or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"error": "filename required"}), 400
    ok = delete_podium_photo(filename)
    return jsonify({"ok": ok})


@admin_bp.route("/admin/photos")
@admin_required
def admin_photos():
    type_filter = request.args.get("type", "")
    photos = get_all_photos(type_filter if type_filter else None)
    return render_template("admin_photos.html", photos=photos, type_filter=type_filter)


@admin_bp.route("/admin/photos/upload", methods=["GET", "POST"])
@admin_required
def admin_photos_upload():
    if request.method == "POST":
        file = request.files.get("photo")
        caption = request.form.get("caption", "").strip()
        photo_type = request.form.get("type", "generic")
        event_id = request.form.get("event_id", "").strip()

        if not file or not file.filename:
            flash("No file selected.")
            return redirect(url_for("admin.admin_photos_upload"))
        if photo_type == "generic" and not caption:
            flash("Caption is required for generic photos.")
            return redirect(url_for("admin.admin_photos_upload"))
        if photo_type == "event" and not event_id:
            flash("Event ID is required for event photos.")
            return redirect(url_for("admin.admin_photos_upload"))

        result = upload_photo(file, caption, photo_type, event_id)
        if result is None:
            flash("Invalid file type. Allowed: JPG, PNG, WebP.")
            return redirect(url_for("admin.admin_photos_upload"))

        flash("Photo uploaded successfully.")
        return redirect(url_for("admin.admin_photos"))

    return render_template("admin_photos_upload.html")


@admin_bp.route("/admin/photos/delete", methods=["POST"])
@admin_required
def admin_photos_delete():
    photo_id = request.form.get("photo_id", "").strip()
    if not photo_id:
        flash("No photo ID provided.")
        return redirect(url_for("admin.admin_photos"))
    ok = delete_club_photo(photo_id)
    flash("Photo deleted." if ok else "Photo not found.")
    return redirect(url_for("admin.admin_photos"))


@admin_bp.route("/admin/refresh-data", methods=["POST"])
@admin_required
def refresh_data_route():
    """Re-download all data/ and tournaments/ files from R2. Use after uploading
    a new scoresheet directly to the bucket, to pick it up without a redeploy."""
    result = r2_service.download_all()
    invalidate_cache()
    if result.get("skipped"):
        flash("R2 is not configured; nothing to refresh.")
    else:
        flash(f"Refreshed {result.get('downloaded', 0)} file(s) from R2.")
    return redirect(url_for("admin.admin_page"))
