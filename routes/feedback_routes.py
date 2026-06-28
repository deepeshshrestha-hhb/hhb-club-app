from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session
)

from routes.admin_routes import admin_required, _safe_next
from services.feedback_service import (
    submit_feedback,
    get_general_feedback,
    get_feature_requests,
    update_status,
    STATUSES,
)

feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.route("/feedback")
def feedback_page():
    """Display feedback. Everyone sees General feedback; admins additionally see
    the Feature Requests column with status controls."""
    is_admin = bool(session.get("is_admin"))
    return render_template(
        "feedback.html",
        general=get_general_feedback(),
        feature_requests=get_feature_requests() if is_admin else None,
        statuses=STATUSES,
    )


@feedback_bp.route("/feedback/submit", methods=["POST"])
def feedback_submit():
    """Accept a feedback submission from the site-wide modal form."""
    row = submit_feedback(
        request.form.get("feedback_type", ""),
        request.form.get("message", ""),
        request.form.get("player", ""),
        request.form.get("email", ""),
    )
    if row is None:
        flash(
            "Please select your name and enter a message "
            "(non-members must also provide an email).",
            "warning",
        )
    else:
        flash("Thanks! Your feedback has been submitted.", "success")
    # Return the user to the page they submitted from (open-redirect safe).
    return redirect(
        _safe_next(request.form.get("next")) or url_for("feedback.feedback_page")
    )


@feedback_bp.route("/feedback/status", methods=["POST"])
@admin_required
def feedback_status():
    """Admin-only: update the status of a feature request."""
    feedback_id = request.form.get("id", "").strip()
    status = request.form.get("status", "").strip()
    if update_status(feedback_id, status):
        flash("Status updated.", "success")
    else:
        flash("Could not update status.", "danger")
    return redirect(url_for("feedback.feedback_page"))
