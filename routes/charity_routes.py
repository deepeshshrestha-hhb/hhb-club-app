from flask import Blueprint, render_template, request, redirect, url_for, flash

from routes.admin_routes import admin_required
from services.charity_service import (
    get_settings,
    set_open,
    set_target,
    get_contributions,
    get_total,
    add_contribution,
    delete_contribution,
)

charity_bp = Blueprint("charity", __name__)


@charity_bp.route("/charity")
def charity_page():
    """Nepal Flood Relief campaign page: write-up, pledge ledger + running
    total, and (while open) a form for members to log a pledge."""
    from services.player_service import get_player_names

    settings = get_settings()
    contributions = get_contributions()
    total = get_total()
    try:
        player_names = get_player_names()
    except Exception:
        player_names = []

    return render_template(
        "charity.html",
        settings=settings,
        contributions=contributions,
        total=total,
        player_names=player_names,
    )


@charity_bp.route("/charity/contribute", methods=["POST"])
def charity_contribute():
    """Log a member's pledge amount against their name."""
    settings = get_settings()
    if not settings.get("is_open"):
        flash("Contributions are currently closed.", "warning")
        return redirect(url_for("charity.charity_page"))

    row = add_contribution(
        request.form.get("member_name", ""),
        request.form.get("amount", ""),
    )
    if row is None:
        flash("Please select your name and enter a valid contribution amount.", "warning")
    else:
        flash(f"Thank you! £{row['Amount']:.2f} logged for {row['Member Name']}.", "success")
    return redirect(url_for("charity.charity_page"))


@charity_bp.route("/charity/delete", methods=["POST"])
@admin_required
def charity_delete():
    """Admin-only: remove a pledge (e.g. wrong name or amount picked)."""
    contribution_id = request.form.get("id", "").strip()
    if delete_contribution(contribution_id):
        flash("Contribution removed.", "success")
    else:
        flash("Could not remove contribution.", "danger")
    return redirect(url_for("charity.charity_page"))


@charity_bp.route("/charity/toggle", methods=["POST"])
@admin_required
def charity_toggle():
    """Admin-only: open or close the campaign for new pledges."""
    set_open(request.form.get("is_open") == "1")
    settings = get_settings()
    flash("Contributions are now open." if settings["is_open"] else "Contributions are now closed.", "success")
    return redirect(url_for("charity.charity_page"))


@charity_bp.route("/charity/target", methods=["POST"])
@admin_required
def charity_set_target():
    """Admin-only: update the fundraising target."""
    if set_target(request.form.get("target_amount", "")):
        flash("Target updated.", "success")
    else:
        flash("Please enter a valid target amount.", "danger")
    return redirect(url_for("charity.charity_page"))
