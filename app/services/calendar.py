# app/services/calendar.py
import logging
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.core.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service():
    """Build and return an authenticated Google Calendar service."""
    creds = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
        client_secret=settings.GOOGLE_CALENDAR_CLIENT_SECRET,
        scopes=SCOPES,
    )
    # Refresh to get a valid access token
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


def _parse_datetime(date_str: str, time_slot: str) -> tuple[datetime, datetime]:
    """
    Convert a date string and time slot like '9:00 AM' into
    start and end datetime objects (30-minute duration).
    date_str format: 'YYYY-MM-DD'
    """
    dt_str = f"{date_str} {time_slot}"
    start = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
    end = start + timedelta(minutes=30)
    return start, end


def create_calendar_event(
    company_name: str,
    employer_name: str,
    employer_email: str,
    date_str: str,
    time_slot: str,
    meeting_url: str,
) -> str | None:
    """
    Create a Google Calendar event for a confirmed booking.
    Returns the calendar event ID, or None on failure.
    """
    try:
        service = _get_calendar_service()
        start, end = _parse_datetime(date_str, time_slot)

        # Format as RFC3339 with EST offset
        tz = "America/New_York"

        event = {
            "summary": f"RYZE Recruiting — {company_name or employer_name}",
            "location": meeting_url,
            "description": (
                f"Recruiter call with {employer_name} from {company_name or 'N/A'}.\n\n"
                f"Zoom: {meeting_url}"
            ),
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": tz,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": tz,
            },
            "attendees": [
                {"email": settings.ADMIN_EMAIL},
                {"email": employer_email},
            ],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 60},
                    {"method": "popup", "minutes": 15},
                ],
            },
            "conferenceData": None,
        }

        created = (
            service.events()
            .insert(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                body=event,
                sendUpdates="all",  # emails attendees
            )
            .execute()
        )

        event_id = created.get("id")
        logger.info(f"Google Calendar event created: {event_id}")
        return event_id

    except Exception as e:
        logger.error(f"Failed to create Google Calendar event: {e}")
        return None


def delete_calendar_event(event_id: str) -> bool:
    """
    Delete a Google Calendar event by ID when a booking is cancelled.
    Returns True on success, False on failure.
    """
    if not event_id:
        return False
    try:
        service = _get_calendar_service()
        service.events().delete(
            calendarId=settings.GOOGLE_CALENDAR_ID,
            eventId=event_id,
            sendUpdates="all",  # notifies attendees of cancellation
        ).execute()
        logger.info(f"Google Calendar event deleted: {event_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete Google Calendar event: {e}")
        return False
