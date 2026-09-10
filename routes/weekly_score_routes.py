from datetime import date

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

from routes.admin_routes import admin_required
from services import weekly_score_service

weekly_bp = Blueprint("weekly_scores", __name__)


@weekly_bp.route("/weekly-scores")
def page():
    state = weekly_score_service.get_state()
    return render_template(
        "weekly_scores.html",
        state=state,
        default_date=weekly_score_service.default_session_date().isoformat(),
    )


@weekly_bp.route("/weekly-scores/api/state")
def api_state():
    return jsonify(weekly_score_service.get_state())


@weekly_bp.route("/weekly-scores/api/matches", methods=["POST"])
def api_add_match():
    fields = request.get_json(silent=True) or request.form
    try:
        weekly_score_service.add_match(fields)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **weekly_score_service.get_state()})


@weekly_bp.route("/weekly-scores/api/matches/<match_id>/amend", methods=["POST"])
def api_amend_match(match_id):
    fields = request.get_json(silent=True) or request.form
    try:
        weekly_score_service.amend_match(match_id, fields)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **weekly_score_service.get_state()})


@weekly_bp.route("/weekly-scores/api/matches/<match_id>/delete", methods=["POST"])
@admin_required
def api_delete_match(match_id):
    try:
        weekly_score_service.delete_match(match_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **weekly_score_service.get_state()})


@weekly_bp.route("/weekly-scores/admin/open", methods=["POST"])
@admin_required
def admin_open():
    date_str = request.form.get("date", "").strip()
    try:
        weekly_score_service.open_session(date_str)
        flash(f"Weekly score session opened for {weekly_score_service.format_display_date(date_str)}.")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("weekly_scores.page"))


@weekly_bp.route("/weekly-scores/admin/close", methods=["POST"])
@admin_required
def admin_close():
    try:
        weekly_score_service.close_session()
        flash("Session closed. Review the scores, then submit to the database.")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("weekly_scores.page"))


@weekly_bp.route("/weekly-scores/admin/submit", methods=["POST"])
@admin_required
def admin_submit():
    try:
        count = weekly_score_service.submit_to_database()
        flash(f"{count} match(es) submitted to the league database.")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("weekly_scores.page"))


@weekly_bp.route("/weekly-scores/admin/debug-players")
@admin_required
def admin_debug_players():
    """Diagnostic view: shows every data source behind the player dropdown
    for a given date (raw CSV rows, historical-cache resolution, live Spond
    resolution, league roster, final result) as JSON, so a live mismatch can
    be pinpointed exactly. ?date=YYYY-MM-DD, defaults to today."""
    date_str = request.args.get("date", "").strip()
    try:
        target_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        return jsonify({"error": "Invalid date, use YYYY-MM-DD."}), 400
    return jsonify(weekly_score_service.debug_player_sources(target_date))
