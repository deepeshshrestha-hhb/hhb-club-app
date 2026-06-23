from flask import Flask, render_template
from config import Config
from routes.calendar_routes import calendar_bp
from routes.tournament_routes import tournament_bp
from routes.admin_routes import admin_bp
from routes.player_routes import player_bp
from services.spond_service import fetch_members_to_csv


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Refresh Spond member list into CSV on every startup
    fetch_members_to_csv()

    # Blueprints
    app.register_blueprint(calendar_bp)
    app.register_blueprint(tournament_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(player_bp)

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
