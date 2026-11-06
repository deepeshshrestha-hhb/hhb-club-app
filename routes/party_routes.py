"""Unlisted Tihar Party RSVP page.

Deliberately not linked from anywhere on the site (navbar, footer, other pages)
and not listed in robots.txt - listing it there would reveal the path. Every
response carries X-Robots-Tag: noindex.
"""
from flask import Blueprint, jsonify, render_template, request

from services import tihar_party_service as tps

party_bp = Blueprint("party", __name__, url_prefix="/party/tihar/hillfield-brae")


@party_bp.after_request
def _noindex(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@party_bp.route("")
def page():
    return render_template(
        "tihar_party.html",
        hide_nav=True,
        hide_feedback=True,
        families=tps.FAMILIES,
        max_people=tps.MAX_PER_FAMILY,
        site_url=tps.SITE_URL,
        state=tps.get_state(),
    )


@party_bp.route("/api/state")
def api_state():
    return jsonify(tps.get_state())


@party_bp.route("/api/respond", methods=["POST"])
def api_respond():
    record, error = tps.save_response(request.get_json(silent=True) or {})
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "record": record, "state": tps.get_state()})
