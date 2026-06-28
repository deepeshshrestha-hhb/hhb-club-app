import math
import datetime
import pandas as pd
from services.excel_service import load_excel
from services.spond_service import get_weekly_sessions as _spond_weekly_sessions


def get_weekly_sessions():
    """Live weekly sessions pulled from Spond (replaces the old Excel-based table)."""
    return _spond_weekly_sessions()


def get_calendar_events():
    df = load_excel("ClubCalendar.xlsx")

    if df.empty:
        return []

    events = []
    for idx, row in df.iterrows():
        events.append(
            {
                "id": idx,
                "title": str(row.get("Title", "Event")),
                "start": str(row.get("Date")),
                "description": str(row.get("Description", "")),
                "type": str(row.get("Type", "general")),
            }
        )
    return events


def _clean(value):
    """Convert NaN/None to empty string, everything else to a clean string."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text


def _format_date_cell(value):
    if isinstance(value, (pd.Timestamp, datetime.date, datetime.datetime)):
        return value.strftime("%d %b").lstrip("0")
    return _clean(value)


def get_annual_event_years():
    """Return sorted list of years for which the annual calendar has date columns."""
    df = load_excel("HHBClubAnnualCalendar.xlsx", header=2)
    if df.empty:
        return []
    years = set()
    for col in df.columns:
        for part in str(col).split():
            if part.isdigit() and len(part) == 4:
                years.add(int(part))
    return sorted(years)


def get_annual_events():
    """
    Reads HHBClubAnnualCalendar.xlsx, which has a title row, then a header row, then
    one row per recurring annual event with columns:
    Event | Description | When | 2026 Dates | 2027 Dates
    """
    df = load_excel("HHBClubAnnualCalendar.xlsx", header=2)

    if df.empty:
        return []

    # Drop the leading blank/unnamed column if present
    cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
    df = df[cols] if cols else df

    # Standardize expected column names (tolerant of slight header variations)
    rename_map = {}
    for c in df.columns:
        key = str(c).strip().lower()
        if key == "event":
            rename_map[c] = "Event"
        elif key == "description":
            rename_map[c] = "Description"
        elif key == "when":
            rename_map[c] = "When"
        elif "2026" in key:
            rename_map[c] = "Dates2026"
        elif "2027" in key:
            rename_map[c] = "Dates2027"
    df = df.rename(columns=rename_map)

    # Events from the 2026 calendar that have already taken place. Update this
    # list as the year progresses (e.g. remove/add names after each event passes).
    COMPLETED_2026_EVENTS = {
        "Annual Championships",
        "Annual Club Holiday",
        "Annual Summer Picnic",
        "Annual Doubles Classic",
    }

    events = []
    for idx, row in df.iterrows():
        name = _clean(row.get("Event"))
        if not name:
            continue  # skip blank rows

        # Excel sometimes stores a date-like cell (e.g. "25 Apr") as an actual
        # date for one year column. Normalize back to a short display string.
        dates_2026 = _format_date_cell(row.get("Dates2026"))
        dates_2027 = _format_date_cell(row.get("Dates2027"))

        events.append(
            {
                "id": idx,
                "name": name,
                "description": _clean(row.get("Description")),
                "when": _clean(row.get("When")),
                "dates_2026": _clean(dates_2026),
                "dates_2027": _clean(dates_2027),
                "completed_2026": name in COMPLETED_2026_EVENTS,
            }
        )
    return events
