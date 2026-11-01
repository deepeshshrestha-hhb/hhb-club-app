"""Unlisted November Group Holiday 2026 availability page.

Deliberately not linked from anywhere on the site (navbar, footer, other
pages) and not listed in robots.txt - listing it there would reveal the path.
Only the exact slug in holiday_service.HOLIDAY_SLUG resolves; anything else
404s. Every response carries X-Robots-Tag: noindex.
"""
from flask import Blueprint, abort, jsonify, make_response, render_template, request, session

from services import holiday_service as hs

holiday_bp = Blueprint("holiday", __name__)


def _check_slug(slug):
    if slug != hs.HOLIDAY_SLUG:
        abort(404)


@holiday_bp.after_request
def _noindex(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@holiday_bp.route("/holiday/nov-2026-<slug>")
def page(slug):
    _check_slug(slug)
    return render_template(
        "holiday_nov2026.html",
        hide_nav=True,
        hide_feedback=True,
        slug=slug,
        weekends=hs.WEEKENDS,
        families=hs.FAMILIES,
        min_people=hs.MIN_PEOPLE,
        min_families=hs.MIN_FAMILIES,
        max_people=hs.MAX_PER_FAMILY,
        note_max=hs.NOTE_MAX,
        site_url=hs.SITE_URL,
        state=hs.get_state(),
        is_admin=bool(session.get("is_admin")),
    )


@holiday_bp.route("/holiday/nov-2026-<slug>/api/state")
def api_state(slug):
    _check_slug(slug)
    return jsonify(hs.get_state())


@holiday_bp.route("/holiday/nov-2026-<slug>/api/respond", methods=["POST"])
def api_respond(slug):
    _check_slug(slug)
    record, error = hs.save_response(request.get_json(silent=True) or {})
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "record": record, "state": hs.get_state()})


# ---- Admin: delete responses (e.g. to start clean after testing) ----------
# Log in via /admin/login?next=/holiday/nov-2026-<slug> - the page has no
# navbar. Returns JSON 403 rather than admin_required's login redirect, since
# these are only called via fetch().

def _require_admin():
    if not session.get("is_admin"):
        abort(make_response(jsonify({"ok": False, "error": "Admin login required."}), 403))


@holiday_bp.route("/holiday/nov-2026-<slug>/api/delete", methods=["POST"])
def api_delete(slug):
    _check_slug(slug)
    _require_admin()
    family = ((request.get_json(silent=True) or {}).get("family") or "").strip()
    if not hs.delete_response(family):
        return jsonify({"ok": False, "error": "No response found for that family."}), 404
    return jsonify({"ok": True, "state": hs.get_state()})


@holiday_bp.route("/holiday/nov-2026-<slug>/api/clear", methods=["POST"])
def api_clear(slug):
    _check_slug(slug)
    _require_admin()
    removed = hs.clear_all()
    return jsonify({"ok": True, "removed": removed, "state": hs.get_state()})
