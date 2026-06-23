from flask import Blueprint, render_template
from services.player_service import get_all_players

player_bp = Blueprint("players", __name__)


@player_bp.route("/players")
def players_page():
    players = get_all_players()
    return render_template("players.html", players=players)
