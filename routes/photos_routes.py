from flask import (
    Blueprint, render_template, abort, request, redirect, url_for, flash, jsonify, session
)

from services.photos_service import get_generic_photos, get_event_photos
from services.event_summary_service import get_summary, save_summary
from services import ai_service
from routes.admin_routes import admin_required

photos_bp = Blueprint("photos", __name__)


def _event_label(event_id: str) -> str:
    """Human-friendly event name from an event_id (e.g. 'Doubles 2025 Photos')."""
    return event_id.replace("_", " ").title()


@photos_bp.route("/photos/gallery")
def gallery():
    photos = get_generic_photos()
    return render_template("photos_gallery.html", photos=photos)


@photos_bp.route("/photos/event/<event_id>")
def event_gallery(event_id):
    photos = get_event_photos(event_id)
    summary = get_summary(event_id)
    # Render when there are photos OR a summary OR the viewer is an admin (so an
    # admin can add a summary before any photos are uploaded).
    if not photos and not summary and not session.get("is_admin"):
        abort(404)
    return render_template(
        "photos_event.html",
        photos=photos,
        event_id=event_id,
        summary=summary,
        ai_enabled=ai_service.is_enabled(),
        ai_presets=ai_service.PRESETS,
    )


@photos_bp.route("/photos/event/<event_id>/summary", methods=["POST"])
@admin_required
def save_event_summary(event_id):
    summary = request.form.get("summary", "")
    save_summary(event_id, summary)
    flash("Event summary saved.")
    return redirect(url_for("photos.event_gallery", event_id=event_id))


@photos_bp.route("/photos/event/<event_id>/summary/ai", methods=["POST"])
@admin_required
def ai_assist(event_id):
    """Run a Claude text-assist instruction against the current draft and return
    the rewritten text as JSON. Admin-only; gracefully reports when disabled."""
    data = request.get_json(silent=True) or {}
    preset = (data.get("preset") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    draft = data.get("draft") or ""

    if preset and preset in ai_service.PRESETS:
        instruction = ai_service.PRESETS[preset]
    if not instruction:
        return jsonify({"error": "No instruction provided."}), 400

    try:
        result = ai_service.assist(instruction, draft, _event_label(event_id))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:  # pragma: no cover - network/SDK failures
        return jsonify({"error": "AI request failed. Please try again."}), 502

    return jsonify({"text": result})
