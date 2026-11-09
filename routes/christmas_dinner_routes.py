"""Unlisted Christmas Dinner 2026 RSVP page.

Deliberately not linked from anywhere on the site (navbar, footer, other pages)
and not listed in robots.txt - listing it there would reveal the path. Every
response carries X-Robots-Tag: noindex.
"""
from flask import Blueprint, jsonify, render_template, request

from services import christmas_dinner_service as cds

christmas_dinner_bp = Blueprint("christmas_dinner", __name__, url_prefix="/party/christmas-dinner-2026")


@christmas_dinner_bp.after_request
def _noindex(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@christmas_dinner_bp.route("")
def page():
    return render_template(
        "christmas_dinner.html",
        hide_nav=True,
        hide_feedback=True,
        families=cds.FAMILIES,
        max_people=cds.MAX_PER_FAMILY,
        venue=cds.VENUE,
        site_url=cds.SITE_URL,
        state=cds.get_state(),
    )


@christmas_dinner_bp.route("/api/state")
def api_state():
    return jsonify(cds.get_state())


@christmas_dinner_bp.route("/api/respond", methods=["POST"])
def api_respond():
    record, error = cds.save_response(request.get_json(silent=True) or {})
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "record": record, "state": cds.get_state()})
