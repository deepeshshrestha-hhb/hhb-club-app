import datetime
from flask import Blueprint, render_template, request, redirect, url_for, abort, send_file, flash, session
from services.player_service import get_all_players
from services.profile_service import (
    get_profile, save_profile, name_to_slug, get_photo_path, get_all_profile_slugs
)

player_bp = Blueprint("players", __name__)

CURRENT_YEAR = datetime.date.today().year
JOIN_YEARS = list(range(CURRENT_YEAR, CURRENT_YEAR - 21, -1))


@player_bp.route("/players")
def players_page():
    players = get_all_players()
    profile_slugs = get_all_profile_slugs()
    return render_template("players.html", players=players, profile_slugs=profile_slugs)


@player_bp.route("/players/<slug>")
def player_profile(slug):
    players = get_all_players()
    player = next((p for p in players if name_to_slug(p["full_name"]) == slug), None)
    if player is None:
        abort(404)
    profile = get_profile(slug)
    return render_template("player_profile.html", player=player, profile=profile, slug=slug)


@player_bp.route("/players/photos/<path:filename>")
def player_photo(filename):
    path = get_photo_path(filename)
    if path is None:
        abort(404)
    return send_file(path)


@player_bp.route("/players/add-profile", methods=["GET", "POST"])
def add_profile():
    players = get_all_players()

    is_admin = session.get("is_admin", False)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Please select a player.", "danger")
            return render_template("player_add_profile.html", players=players,
                                   join_years=JOIN_YEARS, form=request.form, is_admin=is_admin)

        # Validate player exists
        if not any(p["full_name"] == full_name for p in players):
            flash("Unknown player selected.", "danger")
            return render_template("player_add_profile.html", players=players,
                                   join_years=JOIN_YEARS, form=request.form, is_admin=is_admin)

        slug = name_to_slug(full_name)
        profile_exists = get_profile(slug) is not None

        # Non-admins must explicitly confirm before overwriting an existing profile
        if profile_exists and not is_admin:
            if request.form.get("confirm_overwrite") != "yes":
                return render_template("player_add_profile.html", players=players,
                                       join_years=JOIN_YEARS, form=request.form,
                                       is_admin=is_admin, overwrite_warning=full_name)

        photo_file = request.files.get("photo")
        ok, err = save_profile(full_name, request.form, photo_file)
        if not ok:
            flash(err, "danger")
            return render_template("player_add_profile.html", players=players,
                                   join_years=JOIN_YEARS, form=request.form, is_admin=is_admin)

        flash(f"Profile saved for {full_name}.", "success")
        return redirect(url_for("players.player_profile", slug=slug))

    # Pre-select player from query param (e.g. from profile page "Edit" link)
    preselect = request.args.get("player", "")
    existing_profile = None
    if preselect:
        slug = name_to_slug(preselect)
        existing_profile = get_profile(slug)

    return render_template("player_add_profile.html", players=players,
                           join_years=JOIN_YEARS, form=existing_profile or {},
                           preselect=preselect, is_admin=is_admin)
