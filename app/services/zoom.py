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


def convert_time(time_slot: str) -> str:
    """Convert '9:00 AM' to '09:00:00' for Zoom API."""
    from datetime import datetime

    t = datetime.strptime(time_slot, "%I:%M %p")
    return t.strftime("%H:%M:%S")
