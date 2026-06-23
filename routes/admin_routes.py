from flask import Blueprint, render_template
from services.spond_service import sync_spond_events

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
def admin_page():
    return render_template("admin.html")


@admin_bp.route("/admin/sync_spond")
def sync_spond_route():
    sync_spond_events()
    return "Spond sync complete (placeholder)"
