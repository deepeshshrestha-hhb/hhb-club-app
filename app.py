import sys
import logging

from flask import Flask, render_template, jsonify
from config import Config
from routes.calendar_routes import calendar_bp
from routes.tournament_routes import tournament_bp
from routes.admin_routes import admin_bp
from routes.player_routes import player_bp
from services import r2_service

# Log to stdout so messages (incl. R2 sync) surface in the Render logs.
# force=True is required because under gunicorn the root logger already has
# handlers, which would otherwise make a plain basicConfig() a silent no-op.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Pull the canonical data files from durable storage (R2) into the local
    # data/ and tournaments/ folders before serving. No-op when R2 isn't
    # configured (local dev), in which case the existing local files are used.
    # (The Spond member list is refreshed on demand via the Admin page, not on
    # every startup - it rarely changes.)
    r2_service.download_all()

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

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


# Exposed at module level so the production server can find it:
#   gunicorn app:app
app = create_app()


if __name__ == "__main__":
    # Local development server only. Never enable debug in production.
    app.run()
