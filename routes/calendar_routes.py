from flask import Blueprint, render_template, jsonify
from services.calendar_service import (
    get_calendar_events,
    get_annual_events,
    get_weekly_sessions,
)

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/calendar")
def calendar_page():
    weekly_sessions = get_weekly_sessions()  # live from Spond
    annual_events = get_annual_events()
    return render_template(
        "calendar.html",
        calendar=weekly_sessions,
        annual_events=annual_events,
    )


@calendar_bp.route("/api/calendar")
def calendar_api():
    # Still reflects ClubCalendar.xlsx for now. Switch to get_weekly_sessions()
    # here too if you want this endpoint to mirror the live Spond data.
    events = get_calendar_events()
    return jsonify(events)
