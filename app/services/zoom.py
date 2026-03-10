# app/services/zoom.py
import httpx
import base64
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"


def get_access_token() -> str:
    """Exchange Client ID + Secret for a short-lived access token."""
    credentials = f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = httpx.post(
        ZOOM_TOKEN_URL,
        params={
            "grant_type": "account_credentials",
            "account_id": settings.ZOOM_ACCOUNT_ID,
        },
        headers={"Authorization": f"Basic {encoded}"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_meeting(topic: str, date: str, time_slot: str) -> dict:
    """Create a Zoom meeting and return the join_url and meeting_id."""
    token = get_access_token()

    payload = {
        "topic": topic,
        "type": 2,  # Scheduled meeting
        "start_time": f"{date}T{convert_time(time_slot)}",
        "duration": 30,
        "timezone": "America/New_York",
        "settings": {
            "waiting_room": False,
            "join_before_host": True,
            "mute_upon_entry": False,
            "auto_recording": "none",
        },
    }

    response = httpx.post(
        f"{ZOOM_API_BASE}/users/me/meetings",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    data = response.json()

    return {
        "join_url": data["join_url"],
        "meeting_id": str(data["id"]),
    }


def get_meeting_summary(meeting_id: str) -> str | None:
    """
    Fetch the AI Companion meeting summary for a completed meeting.
    Returns the summary text or None if not available yet.
    """
    try:
        token = get_access_token()
        response = httpx.get(
            f"{ZOOM_API_BASE}/meetings/{meeting_id}/meeting_summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 404:
            logger.info(f"No summary available yet for meeting {meeting_id}")
            return None

        if response.status_code != 200:
            logger.warning(
                f"Zoom summary API returned {response.status_code} for meeting {meeting_id}: {response.text}"
            )
            return None

        data = response.json()
        logger.info(f"Zoom summary API response for {meeting_id}: {data}")

        # Try the most common response shapes Zoom uses
        summary_text = (
            data.get("summary_overview")
            or data.get("summary")
            or data.get("meeting_summary")
            or ""
        )

        # Sometimes it's nested under a "summary" object
        if not summary_text and isinstance(data.get("summary"), dict):
            summary_text = data["summary"].get("summary_overview") or data[
                "summary"
            ].get("summary", "")

        return summary_text or None

    except Exception as e:
        logger.error(f"Failed to fetch Zoom meeting summary for {meeting_id}: {e}")
        return None


def convert_time(time_slot: str) -> str:
    """Convert '9:00 AM' to '09:00:00' for Zoom API."""
    from datetime import datetime

    t = datetime.strptime(time_slot, "%I:%M %p")
    return t.strftime("%H:%M:%S")
