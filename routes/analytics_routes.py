"""
Public JSON analytics endpoints for player signup activity (hours played).

All three read from player_service.get_all_players(), which already carries the
hours_last_four_weeks / hours_last_six_months fields merged from
data/player_hours.csv. The underlying data is refreshed via the admin
"Refresh Signup Analytics" action (see admin_routes.refresh_signups_route).
"""
from flask import Blueprint, jsonify, abort

from services.player_service import get_all_players
from services.profile_service import name_to_slug

analytics_bp = Blueprint("analytics", __name__)

TOP_N = 20


def _summary(player):
    return {
        "full_name": player["full_name"],
        "hours_last_four_weeks": player.get("hours_last_four_weeks", 0.0),
        "hours_last_six_months": player.get("hours_last_six_months", 0.0),
    }


@analytics_bp.route("/api/analytics/most-active")
def most_active():
    """Top 20 players by hours played in the last six months (descending)."""
    players = sorted(
        get_all_players(),
        key=lambda p: p.get("hours_last_six_months", 0.0),
        reverse=True,
    )
    return jsonify([_summary(p) for p in players[:TOP_N]])


@analytics_bp.route("/api/analytics/inactive")
def inactive():
    """Players with zero hours played in the last six months."""
    players = [
        p for p in get_all_players()
        if p.get("hours_last_six_months", 0.0) == 0
    ]
    players.sort(key=lambda p: p["full_name"].casefold())
    return jsonify([_summary(p) for p in players])


@analytics_bp.route("/api/analytics/player/<slug>/four-weeks")
def player_four_weeks(slug):
    """A single player's last-four-weeks hours, for their profile card."""
    player = next(
        (p for p in get_all_players() if name_to_slug(p["full_name"]) == slug),
        None,
    )
    if player is None:
        abort(404)
    return jsonify({
        "full_name": player["full_name"],
        "hours_last_four_weeks": player.get("hours_last_four_weeks", 0.0),
    })
