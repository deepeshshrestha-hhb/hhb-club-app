from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash

from routes.admin_routes import admin_required
from services import sunday_pools_service

sunday_pools_bp = Blueprint("sunday_pools", __name__)


def _default_date():
    """The coming Sunday (or today, if today is already Sunday) - a sensible
    starting point for the admin's date picker."""
    today = date.today()
    if today.weekday() == 6:
        return today
    return today + timedelta(days=(6 - today.weekday()) % 7)


@sunday_pools_bp.route("/sunday-pools")
def sunday_pools_page():
    """Public page showing the most recently generated Sunday Pool A / Pool B
    (10-11am), or a specific past date via ?date=YYYY-MM-DD. The admin
    generate-pools form lives on this same page, visible to admins only."""
    requested = request.args.get("date", "").strip()
    if requested:
        pools = sunday_pools_service.get_pools_for_date(requested)
        shown_date = requested if pools else None
    else:
        shown_date, pools = sunday_pools_service.get_latest_pools()
    return render_template(
        "sunday_pools.html",
        shown_date=shown_date,
        pools=pools,
        generated_dates=sunday_pools_service.list_generated_dates(),
        default_date=_default_date().isoformat(),
    )


@sunday_pools_bp.route("/sunday-pools/generate", methods=["POST"])
@admin_required
def generate_sunday_pools():
    date_str = request.form.get("date", "").strip()
    try:
        sunday_pools_service.generate_pools(date_str)
        flash(f"Pool A / Pool B generated and published for {date_str}.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sunday_pools.sunday_pools_page"))
    return redirect(url_for("sunday_pools.sunday_pools_page", date=date_str))
