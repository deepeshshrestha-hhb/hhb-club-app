"""HHB Annual Dinner & Gala 2026 - /annual-dinner.

Public: page, live state, RSVP upsert, claim an open volunteer role (JSON).
Admin (admin_required, plain form posts that redirect back to the page):
venue/target settings, role assign/rename/add/remove, champion overrides,
RSVP delete, CSV/Excel export.
"""
import csv
import io

from flask import (Blueprint, Response, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

from routes.admin_routes import admin_required
from services import annual_dinner_service as ads
from services.player_service import get_player_names

annual_dinner_bp = Blueprint("annual_dinner", __name__, url_prefix="/annual-dinner")


def _back(anchor="admin"):
    return redirect(url_for("annual_dinner.page") + f"#{anchor}")


def _flash(error, ok_msg):
    flash(error or ok_msg, "danger" if error else "success")


@annual_dinner_bp.route("")
def page():
    is_admin = bool(session.get("is_admin"))
    return render_template(
        "annual_dinner.html",
        ev={
            "title": ads.EVENT_TITLE,
            "start_iso": ads.EVENT_START_ISO,
            "date": ads.EVENT_DATE_DISPLAY,
            "time": ads.EVENT_TIME_DISPLAY,
        },
        site_url=ads.SITE_URL,
        members=get_player_names(),
        max_per_band=ads.MAX_PER_BAND,
        state=ads.get_state(),
        champions=ads.get_champions(),
        admin=ads.get_admin_data() if is_admin else None,
        is_admin=is_admin,
    )


@annual_dinner_bp.route("/api/state")
def api_state():
    return jsonify(ads.get_state())


@annual_dinner_bp.route("/api/rsvp")
def api_get_rsvp():
    return jsonify({"rsvp": ads.get_rsvp((request.args.get("member") or "").strip())})


@annual_dinner_bp.route("/api/rsvp", methods=["POST"])
def api_save_rsvp():
    record, error = ads.save_rsvp(request.get_json(silent=True) or {})
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "rsvp": record, "state": ads.get_state()})


@annual_dinner_bp.route("/api/roles/<int:role_id>/claim", methods=["POST"])
def api_claim_role(role_id):
    error = ads.claim_role(role_id, (request.get_json(silent=True) or {}).get("member"))
    if error:
        return jsonify({"ok": False, "error": error, "state": ads.get_state()}), 400
    return jsonify({"ok": True, "state": ads.get_state()})


# ---------------------------------------------------------------- admin ----

@annual_dinner_bp.route("/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    _flash(ads.admin_save_settings(request.form), "Event settings saved.")
    return _back()


@annual_dinner_bp.route("/admin/toggle-banner", methods=["POST"])
@admin_required
def admin_toggle_banner():
    on = request.form.get("visible") == "1"
    ads.set_banner_visible(on)
    flash("Annual Dinner banner is now showing on the Dashboard." if on
          else "Annual Dinner banner hidden from the Dashboard.", "success")
    return redirect(url_for("admin.admin_page"))


@annual_dinner_bp.route("/admin/roles/add", methods=["POST"])
@admin_required
def admin_role_add():
    _flash(ads.admin_add_role(request.form.get("role")), "Role added.")
    return _back("roles")


@annual_dinner_bp.route("/admin/roles/<int:role_id>/assign", methods=["POST"])
@admin_required
def admin_role_assign(role_id):
    _flash(ads.admin_set_holder(role_id, request.form.get("holder")), "Role updated.")
    return _back("roles")


@annual_dinner_bp.route("/admin/roles/<int:role_id>/rename", methods=["POST"])
@admin_required
def admin_role_rename(role_id):
    _flash(ads.admin_rename_role(role_id, request.form.get("role")), "Role renamed.")
    return _back("roles")


@annual_dinner_bp.route("/admin/roles/<int:role_id>/remove", methods=["POST"])
@admin_required
def admin_role_remove(role_id):
    ads.admin_remove_role(role_id)
    flash("Role removed.", "success")
    return _back("roles")


@annual_dinner_bp.route("/admin/champions/set", methods=["POST"])
@admin_required
def admin_champion_set():
    _flash(ads.admin_set_champion(request.form.get("event"), request.form.get("winners")),
           "Champions list updated.")
    return _back("champions")


@annual_dinner_bp.route("/admin/champions/remove", methods=["POST"])
@admin_required
def admin_champion_remove():
    ads.admin_remove_champion_override(request.form.get("event"))
    flash("Override removed.", "success")
    return _back("champions")


@annual_dinner_bp.route("/admin/rsvp/delete", methods=["POST"])
@admin_required
def admin_rsvp_delete():
    ads.delete_rsvp((request.form.get("member") or "").strip())
    flash("RSVP deleted.", "success")
    return _back()


@annual_dinner_bp.route("/admin/export.csv")
@admin_required
def admin_export_csv():
    rows = ads.export_rows()
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return Response(
        "﻿" + buf.getvalue(),  # BOM so Excel opens it as UTF-8
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=annual_dinner_2026_rsvps.csv"},
    )


@annual_dinner_bp.route("/admin/export.xlsx")
@admin_required
def admin_export_xlsx():
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame(ads.export_rows()).to_excel(buf, index=False, sheet_name="RSVPs")
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="annual_dinner_2026_rsvps.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
