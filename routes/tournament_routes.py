from flask import Blueprint, render_template, request, redirect, url_for
from services.tournament_service import (
    get_all_tournaments,
    get_tournament_by_id,
    create_tournament,
    list_doubles_tournament_years,
    get_doubles_tournament,
)
from services.championship_service import list_championship_years, get_championship
from services.league_service import list_league_years, get_league

tournament_bp = Blueprint("tournaments", __name__)


@tournament_bp.route("/tournaments")
def tournaments_page():
    tournaments = get_all_tournaments()
    return render_template("tournaments.html", tournaments=tournaments)


@tournament_bp.route("/tournaments/<int:tournament_id>")
def tournament_detail_page(tournament_id):
    tournament = get_tournament_by_id(tournament_id)
    if not tournament:
        return "Tournament not found", 404
    return render_template("tournament_detail.html", tournament=tournament)


@tournament_bp.route("/tournaments/create", methods=["POST"])
def create_tournament_route():
    name = request.form.get("name")
    date = request.form.get("date")
    if not name or not date:
        return redirect(url_for("tournaments.tournaments_page"))

    create_tournament(name, date)
    return redirect(url_for("tournaments.tournaments_page"))


@tournament_bp.route("/tournaments/annual")
def annual_tournaments_hub():
    return render_template("annual_tournaments.html")


# --- HHB Annual Doubles Classic archive ---

@tournament_bp.route("/tournaments/doubles")
def doubles_index():
    years = list_doubles_tournament_years()
    tournaments = []
    for year in years:
        data = get_doubles_tournament(year)
        ready = bool(data and data["groups"])
        tournaments.append({
            "year": year,
            "ready": ready,
            "winner": data["knockouts"]["winner"] if (data and data["knockouts"]) else "",
            "runner_up": data["knockouts"]["runner_up"] if (data and data["knockouts"]) else "",
        })
    return render_template(
        "tournament_doubles_index.html",
        tournaments=tournaments,
    )


@tournament_bp.route("/tournaments/doubles/<int:year>")
def doubles_detail(year):
    tournament = get_doubles_tournament(year)
    if not tournament:
        return "Tournament not found", 404
    years = sorted(list_doubles_tournament_years())
    idx = years.index(year) if year in years else -1
    prev_year = years[idx - 1] if idx > 0 else None
    next_year = years[idx + 1] if idx >= 0 and idx < len(years) - 1 else None
    return render_template("tournament_doubles_detail.html", tournament=tournament,
                           prev_year=prev_year, next_year=next_year)


# --- HHB Annual Championships ---

@tournament_bp.route("/tournaments/championships")
def championships_index():
    years = list_championship_years()
    championships = []
    for year in years:
        data = get_championship(year)
        championships.append({
            "year": year,
            "pool_a_winner": data["pool_a"]["knockouts"]["winner"] if data else "",
            "pool_a_runner_up": data["pool_a"]["knockouts"]["runner_up"] if data else "",
            "pool_b_winner": data["pool_b"]["knockouts"]["winner"] if data else "",
            "pool_b_runner_up": data["pool_b"]["knockouts"]["runner_up"] if data else "",
        })
    return render_template("championships_index.html", championships=championships)


@tournament_bp.route("/tournaments/championships/<int:year>")
def championships_detail(year):
    championship = get_championship(year)
    if not championship:
        return "Championship not found", 404
    years = sorted(list_championship_years())
    idx = years.index(year) if year in years else -1
    prev_year = years[idx - 1] if idx > 0 else None
    next_year = years[idx + 1] if idx >= 0 and idx < len(years) - 1 else None
    return render_template("championships_detail.html", championship=championship,
                           prev_year=prev_year, next_year=next_year)


# --- HHB Annual Doubles League ---

@tournament_bp.route("/tournaments/league")
def league_index():
    years = list_league_years()
    leagues = []
    for year in years:
        data = get_league(year)
        leagues.append({
            "year": year,
            "winner": data["winner"] if data else "",
            "runner_up": data["runner_up"] if data else "",
            "season_start": data["season_start"] if data else "",
            "season_end": data["season_end"] if data else "",
            "status": data["status"] if data else "complete",
            "off_dates": data["off_dates"] if data else [],
        })
    return render_template("league_index.html", leagues=leagues)


@tournament_bp.route("/tournaments/league/<int:year>")
def league_detail(year):
    league = get_league(year)
    if not league:
        return "League not found", 404
    years = sorted(list_league_years())
    idx = years.index(year) if year in years else -1
    prev_year = years[idx - 1] if idx > 0 else None
    next_year = years[idx + 1] if idx >= 0 and idx < len(years) - 1 else None
    return render_template("league_detail.html", league=league,
                           prev_year=prev_year, next_year=next_year)
