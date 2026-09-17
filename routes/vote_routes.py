from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash

from routes.admin_routes import admin_required
from services import vote_service, club_rankings_service

vote_bp = Blueprint("vote", __name__)


@vote_bp.route("/vote")
def page():
    state = vote_service.get_state()
    return render_template(
        "vote.html",
        candidates=vote_service.get_candidates(),
        voter_names=vote_service.get_voter_names(),
        voting_open=state["voting_open"],
    )


@vote_bp.route("/vote/api/status")
def api_status():
    """Whether `member` has already voted - never their picks, so simply
    picking a name from the dropdown can't leak someone else's ballot."""
    member = request.args.get("member", "").strip()
    if member not in vote_service.get_voter_names():
        return jsonify({"has_voted": False})
    return jsonify({"has_voted": vote_service.has_voted(member)})


@vote_bp.route("/vote/api/verify", methods=["POST"])
def api_verify():
    """Unlocks an existing ballot for viewing/editing given the right PIN."""
    body = request.get_json(silent=True) or {}
    member = (body.get("member_name") or "").strip()
    pin = (body.get("pin") or "").strip()
    rankings = vote_service.get_vote_with_pin(member, pin)
    if rankings is None:
        return jsonify({"ok": False, "error": "Incorrect PIN."}), 400
    return jsonify({"ok": True, "rankings": rankings})


@vote_bp.route("/vote", methods=["POST"])
def submit():
    body = request.get_json(silent=True) or {}
    ok, reason, new_pin = vote_service.submit_vote(
        body.get("member_name", ""), body.get("rankings") or [], body.get("pin")
    )
    if not ok:
        return jsonify({"ok": False, "error": reason}), 400
    return jsonify({"ok": True, "pin": new_pin})


@vote_bp.route("/vote/results")
def results():
    state = vote_service.get_state()
    voted, total = vote_service.get_progress()
    is_admin = bool(session.get("is_admin"))
    show_leaderboard = state["results_published"] or is_admin
    return render_template(
        "vote_results.html",
        voted=voted,
        total=total,
        results_published=state["results_published"],
        is_admin=is_admin,
        show_leaderboard=show_leaderboard,
        leaderboard=vote_service.get_leaderboard() if show_leaderboard else None,
        all_votes=vote_service.admin_get_all_votes() if is_admin else None,
    )


@vote_bp.route("/vote/admin/apply-rankings", methods=["POST"])
@admin_required
def admin_apply_rankings():
    """Reorders the Club Rankings Top 20 to match the vote's current
    leaderboard - the one-click step for "voting has finished, make it the
    new Club Rankings order" once the admin is happy with the result."""
    leaderboard = vote_service.get_leaderboard()
    order = [r["name"] for r in leaderboard]
    if club_rankings_service.apply_vote_order(order):
        flash("Club Rankings Top 20 updated to match the vote results.", "success")
    else:
        flash("Could not apply the vote results to Club Rankings.", "danger")
    return redirect(url_for("vote.results"))


@vote_bp.route("/vote/admin/clear-vote", methods=["POST"])
@admin_required
def admin_clear_vote():
    member = request.form.get("member_name", "").strip()
    ok = vote_service.admin_clear_vote(member)
    flash(f"Cleared {member}'s vote - they can vote again from scratch." if ok else "That member hadn't voted.")
    return redirect(url_for("vote.results"))


@vote_bp.route("/vote/admin/toggle-voting", methods=["POST"])
@admin_required
def toggle_voting():
    vote_service.set_voting_open(request.form.get("open") == "1")
    return redirect(url_for("admin.admin_page"))


@vote_bp.route("/vote/admin/toggle-publish", methods=["POST"])
@admin_required
def toggle_publish():
    vote_service.set_results_published(request.form.get("published") == "1")
    return redirect(url_for("admin.admin_page"))
