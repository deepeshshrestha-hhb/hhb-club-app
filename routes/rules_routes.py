from flask import Blueprint, render_template, request, redirect, url_for, flash

from services import club_rules_service
from routes.admin_routes import admin_required

rules_bp = Blueprint("rules", __name__)


@rules_bp.route("/rules")
def club_rules():
    return render_template(
        "club_rules.html",
        rules_content=club_rules_service.get_rules_content(),
        rules_sections=club_rules_service.SECTION_ORDER,
        rules_section_titles=club_rules_service.SECTION_TITLES,
    )


@rules_bp.route("/rules/section/<key>", methods=["POST"])
@admin_required
def update_rules_section(key):
    ok = club_rules_service.update_section(key, request.form.get("content", ""))
    flash("Club Rules section updated." if ok else "Unknown section.")
    return redirect(url_for("rules.club_rules") + f"?open={key}")
