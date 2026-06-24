import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import Config

try:
    from spond import spond
except ImportError:
    spond = None

LOCAL_TZ = ZoneInfo("Europe/London")


def sync_spond_events():
    # Kept for backwards compatibility with the Admin "Sync Spond" button.
    # Live-fetch mode means there's nothing to pre-sync; data is pulled
    # fresh whenever the Calendar page is loaded (see get_weekly_sessions below).
    print("Spond sync placeholder called (live-fetch mode - no sync needed).")


async def _fetch_member_names(s, group_id):
    """Build a map of member id -> first name for the group, used to show
    confirmed attendee names against each event."""
    try:
        group = await s.get_group(group_id)
    except Exception as exc:
        print(f"Spond member lookup failed: {exc}")
        return {}

    names = {}
    for member in group.get("members", []) or []:
        member_id = member.get("id")
        first_name = member.get("firstName", "")
        last_name = member.get("lastName", "")
        last_initial = f"{last_name[0]}." if last_name else ""
        display_name = f"{first_name} {last_initial}".strip()
        if member_id:
            names[member_id] = display_name
    return names


async def _fetch_events_async(weeks_ahead=8):
    """Fetch upcoming events (today onwards) from Spond for the configured group."""
    if spond is None:
        raise RuntimeError(
            "The 'spond' package is not installed. Run: pip install spond"
        )

    username = Config.SPOND_USERNAME
    password = Config.SPOND_PASSWORD
    group_id = Config.SPOND_GROUP_ID

    if not username or "your_email" in username:
        raise RuntimeError(
            "Spond credentials are not set. Update SPOND_USERNAME, SPOND_PASSWORD "
            "and SPOND_GROUP_ID in config.py."
        )

    s = spond.Spond(username=username, password=password)
    try:
        # Start of today, so today's sessions still show but anything earlier today
        # that's already finished is excluded along with all past days.
        min_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        max_start = datetime.now() + timedelta(weeks=weeks_ahead)
        events = await s.get_events(
            group_id=group_id,
            min_start=min_start,
            max_start=max_start,
            include_scheduled=True,
        )
        member_names = await _fetch_member_names(s, group_id)
    finally:
        await s.clientsession.close()

    return events or [], member_names


def _parse_timestamp(value):
    if not value:
        return None
    try:
        # Spond timestamps are typically ISO 8601 UTC, e.g. "2026-06-21T08:00:00Z"
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(LOCAL_TZ)
    except (ValueError, AttributeError):
        return None


def _format_event(ev, member_names):
    start = _parse_timestamp(ev.get("startTimestamp"))

    responses = ev.get("responses") or {}
    accepted = responses.get("acceptedIds") or []
    names = [member_names.get(uid, "") for uid in accepted]
    names = [n for n in names if n]

    return {
        "date": start.strftime("%Y-%m-%d") if start else "TBC",
        "day": start.strftime("%A") if start else "",
        "start_time": start.strftime("%H:%M") if start else "",
        "session": ev.get("heading", "Session"),
        "confirmed": len(accepted),
        "names": names,
    }


async def _fetch_members_async():
    """Fetch all members of the HHB Members subgroup from Spond."""
    if spond is None:
        raise RuntimeError("spond package not installed")
    s = spond.Spond(username=Config.SPOND_USERNAME, password=Config.SPOND_PASSWORD)
    try:
        group = await s.get_group(Config.SPOND_GROUP_ID)
        # Find HHB Members subgroup ID by name
        hhb_sg_id = None
        for sg in group.get("subGroups", []):
            if "hhb members" in sg.get("name", "").lower():
                hhb_sg_id = sg.get("id")
                break

        members = []
        for m in group.get("members", []):
            if hhb_sg_id and hhb_sg_id not in m.get("subGroups", []):
                continue
            dob = m.get("dateOfBirth", "") or ""
            members.append({
                "first_name": m.get("firstName", ""),
                "last_name": m.get("lastName", ""),
                "full_name": f"{m.get('firstName', '')} {m.get('lastName', '')}".strip(),
                "email": m.get("email", ""),
                "dob": dob,
            })
        return sorted(members, key=lambda x: x["first_name"])
    finally:
        await s.clientsession.close()


def fetch_members_to_csv():
    """Fetch Spond HHB Members and write to data/hhb_members.csv on app startup.
    Fails silently so app still starts if Spond is unreachable."""
    import csv, os
    csv_path = os.path.join(Config.DATA_DIR, "hhb_members.csv")
    try:
        members = asyncio.run(_fetch_members_async())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["first_name", "last_name", "full_name", "email", "dob"])
            writer.writeheader()
            writer.writerows(members)
        print(f"Spond: {len(members)} HHB members written to {csv_path}")
        # Persist the refreshed member list to R2 (no-op when R2 isn't configured).
        from services import r2_service
        r2_service.upload_file(csv_path)
    except Exception as exc:
        print(f"Spond member fetch skipped (using cached CSV): {exc}")


def get_weekly_sessions(weeks_ahead=8):
    """
    Synchronous wrapper that fetches live Spond events (today onwards) and returns
    them in the {date, day, start_time, session, confirmed, names} shape expected
    by calendar.html's weekly table. Returns an empty list (rather than raising) if
    Spond is unreachable, so the page still renders.
    """
    try:
        events, member_names = asyncio.run(_fetch_events_async(weeks_ahead))
    except Exception as exc:
        print(f"Spond fetch failed: {exc}")
        return []

    formatted = [_format_event(ev, member_names) for ev in events]
    formatted.sort(key=lambda e: (e["date"], e["start_time"]))
    return formatted
