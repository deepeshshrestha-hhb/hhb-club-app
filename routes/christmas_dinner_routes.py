"""Unlisted Christmas Dinner 2026 RSVP page.

Deliberately not linked from anywhere on the site (navbar, footer, other pages)
and not listed in robots.txt - listing it there would reveal the path. Every
response carries X-Robots-Tag: noindex.
"""
from flask import (Blueprint, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from routes.admin_routes import admin_required
from services import christmas_dinner_service as cds
from services import xmas2026_preorder_service as xps

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


# --------------------------------------------------------------------------
# Meal pre-order & payment tracker (/preorder) - same blueprint, so the same
# noindex header and the same "unlisted" rule apply. The only link to it is the
# button on the RSVP page above.
# --------------------------------------------------------------------------

def _preorder_ctx(state):
    return dict(hide_nav=True, hide_feedback=True, ev=xps.EVENT, state=state,
                is_admin=bool(session.get("is_admin")), site_url=cds.SITE_URL)


@christmas_dinner_bp.route("/preorder")
def preorder_page():
    return render_template("xmas_preorder.html", menu=xps.menu_for_template(),
                           families=xps.FAMILIES, notes_max=xps.NOTES_MAX, **_preorder_ctx(xps.get_state()))


@christmas_dinner_bp.route("/preorder/state")
def preorder_state():
    return jsonify(xps.get_state())


@christmas_dinner_bp.route("/preorder/save", methods=["POST"])
def preorder_save():
    order, error = xps.save_order(request.get_json(silent=True) or {}, is_admin=bool(session.get("is_admin")))
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "order": order, "state": xps.get_state()})


@christmas_dinner_bp.route("/preorder/paid", methods=["POST"])
def preorder_paid():
    _, error = xps.set_paid(request.get_json(silent=True) or {})
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "state": xps.get_state()})


@christmas_dinner_bp.route("/preorder/summary")
def preorder_summary():
    """Kitchen summary + all-orders table. ?partial=1 returns just the fragment
    the main page swaps in after a save; otherwise a standalone printable page."""
    state = xps.get_state()
    if request.args.get("partial"):
        return render_template("_xmas_preorder_summary.html", **_preorder_ctx(state))
    return render_template("xmas_preorder_summary.html", **_preorder_ctx(state))


@christmas_dinner_bp.route("/preorder/export")
def preorder_export():
    return send_file(xps.export_workbook(), as_attachment=True,
                     download_name="christmas-lunch-2026-orders.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@christmas_dinner_bp.route("/preorder/lock", methods=["POST"])
@admin_required
def preorder_lock():
    xps.set_locked(request.form.get("locked") == "on")
    return redirect(url_for("christmas_dinner.preorder_page") + "#admin")
