from flask import Blueprint, render_template, jsonify
from services.calendar_service import (
    get_calendar_events,
    get_annual_events,
    get_weekly_sessions,
)
from services.photos_service import get_all_photos

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/calendar")
def calendar_page():
    weekly_sessions = get_weekly_sessions()  # live from Spond
    annual_events = get_annual_events()
    # Build the set of event_ids that have at least one photo uploaded,
    # so the template can show a "View Photos" link next to the matching year.
    photo_event_ids = {
        p["event_id"] for p in get_all_photos(type_filter="event") if p["event_id"]
    }
    return render_template(
        "calendar.html",
        calendar=weekly_sessions,
        annual_events=annual_events,
        photo_event_ids=photo_event_ids,
    )


@calendar_bp.route("/api/calendar")
def calendar_api():
    # Still reflects ClubCalendar.xlsx for now. Switch to get_weekly_sessions()
    # here too if you want this endpoint to mirror the live Spond data.
    events = get_calendar_events()
    return jsonify(events)
