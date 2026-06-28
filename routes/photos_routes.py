from flask import Blueprint, render_template, abort

from services.photos_service import get_generic_photos, get_event_photos

photos_bp = Blueprint("photos", __name__)


@photos_bp.route("/photos/gallery")
def gallery():
    photos = get_generic_photos()
    return render_template("photos_gallery.html", photos=photos)


@photos_bp.route("/photos/event/<event_id>")
def event_gallery(event_id):
    photos = get_event_photos(event_id)
    if not photos:
        abort(404)
    return render_template("photos_event.html", photos=photos, event_id=event_id)
