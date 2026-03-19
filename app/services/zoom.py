# app/services/zoom.py
import httpx
import base64
import logging
import re
from urllib.parse import quote
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
            "auto_recording": "cloud",  # enables cloud recording + transcript
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


def get_meeting_data(meeting_uuid: str) -> dict:
    """
    Fetch the full AI Companion summary data for a completed meeting.
    Returns a dict with keys: summary, next_steps, keywords.
    All values are strings or None.
    """
    try:
        token = get_access_token()
        encoded_uuid = quote(quote(meeting_uuid, safe=""), safe="")

        response = httpx.get(
            f"{ZOOM_API_BASE}/meetings/{encoded_uuid}/meeting_summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        logger.info(
            f"Zoom summary API status {response.status_code} for UUID {meeting_uuid}"
        )

        if response.status_code == 404:
            logger.info(f"No summary available for meeting {meeting_uuid}")
            return {}

        if response.status_code != 200:
            logger.warning(
                f"Zoom summary API returned {response.status_code}: {response.text}"
            )
            return {}

        data = response.json()
        logger.info(f"Zoom summary API response keys: {list(data.keys())}")

        # ── Overview / summary ────────────────────────────────────────────
        summary = (
            data.get("summary_overview")
            or data.get("summary")
            or data.get("meeting_summary")
            or ""
        )
        if not summary and isinstance(data.get("summary"), dict):
            summary = data["summary"].get("summary_overview") or data["summary"].get(
                "summary", ""
            )

        # ── Summary details (topic breakdown appended to summary) ─────────
        summary_details = data.get("summary_details", [])
        if summary_details and isinstance(summary_details, list):
            detail_parts = []
            for detail in summary_details:
                if isinstance(detail, dict):
                    label = detail.get("label") or detail.get("title") or ""
                    content = detail.get("summary") or detail.get("content") or ""
                    if label and content:
                        detail_parts.append(f"{label}: {content}")
                    elif content:
                        detail_parts.append(content)
            if detail_parts:
                summary = summary + "\n\n" + "\n".join(detail_parts)

        # ── Next steps ────────────────────────────────────────────────────
        raw_next_steps = data.get("next_steps", [])
        if isinstance(raw_next_steps, list):
            next_steps_parts = []
            for item in raw_next_steps:
                if isinstance(item, dict):
                    text = (
                        item.get("summary")
                        or item.get("text")
                        or item.get("item")
                        or str(item)
                    )
                else:
                    text = str(item)
                next_steps_parts.append(f"• {text}")
            next_steps = "\n".join(next_steps_parts)
        else:
            next_steps = str(raw_next_steps) if raw_next_steps else ""

        # ── Keywords ──────────────────────────────────────────────────────
        raw_keywords = data.get("keywords", [])
        if isinstance(raw_keywords, list):
            keywords = ", ".join(str(k) for k in raw_keywords)
        else:
            keywords = str(raw_keywords) if raw_keywords else ""

        return {
            "summary": summary.strip() or None,
            "next_steps": next_steps.strip() or None,
            "keywords": keywords.strip() or None,
        }

    except Exception as e:
        logger.error(f"Failed to fetch Zoom meeting summary for {meeting_uuid}: {e}")
        return {}


def download_recording_file(download_url: str, download_token: str) -> str | None:
    """
    Download a Zoom recording file using the download_token from the
    recording.completed webhook payload.

    This is the correct way to fetch a transcript when handling
    recording.completed — the download_token is scoped to these exact files
    and valid for 24 hours, so we don't need to exchange credentials.

    For TRANSCRIPT files, the content is VTT format — parsed to plain text
    before returning.
    """
    try:
        response = httpx.get(
            f"{download_url}?access_token={download_token}",
            follow_redirects=True,
            timeout=30.0,
        )

        logger.info(
            f"Recording file download status {response.status_code} "
            f"for URL {download_url[:60]}…"
        )

        if response.status_code != 200:
            logger.warning(
                f"Failed to download recording file: HTTP {response.status_code}"
            )
            return None

        content = response.text
        if not content or not content.strip():
            logger.warning("Recording file download returned empty content")
            return None

        # Detect VTT format and parse to plain text
        if content.strip().startswith("WEBVTT"):
            parsed = _parse_vtt_transcript(content)
            logger.info(f"VTT transcript parsed: {len(parsed)} chars")
            return parsed or None

        # Non-VTT content (e.g. chat file) — return as-is
        return content.strip() or None

    except Exception as e:
        logger.error(f"Failed to download recording file: {e}")
        return None


def get_meeting_transcript(meeting_id: str) -> str | None:
    """
    Fallback: poll the recordings API to fetch a transcript.

    Prefer download_recording_file() when handling recording.completed —
    it uses the download_token from the webhook payload directly.

    This function is kept as a fallback for cases where the download_token
    is unavailable or the recording.completed webhook was missed.
    """
    try:
        token = get_access_token()

        response = httpx.get(
            f"{ZOOM_API_BASE}/meetings/{meeting_id}/recordings",
            headers={"Authorization": f"Bearer {token}"},
        )

        logger.info(
            f"Zoom recordings API status {response.status_code} for meeting {meeting_id}"
        )

        if response.status_code != 200:
            logger.info(f"No recordings found for meeting {meeting_id}")
            return None

        data = response.json()
        recording_files = data.get("recording_files", [])

        transcript_url = None
        for file in recording_files:
            file_type = file.get("file_type", "").upper()
            recording_type = file.get("recording_type", "")
            if file_type == "TRANSCRIPT" or recording_type == "audio_transcript":
                transcript_url = file.get("download_url")
                break

        if not transcript_url:
            logger.info(f"No transcript file in recordings for meeting {meeting_id}")
            return None

        transcript_response = httpx.get(
            f"{transcript_url}?access_token={token}",
            follow_redirects=True,
        )

        if transcript_response.status_code != 200:
            logger.warning(
                f"Failed to download transcript: {transcript_response.status_code}"
            )
            return None

        transcript = _parse_vtt_transcript(transcript_response.text)
        logger.info(
            f"Transcript fetched for meeting {meeting_id}: {len(transcript)} chars"
        )
        return transcript or None

    except Exception as e:
        logger.error(f"Failed to fetch transcript for meeting {meeting_id}: {e}")
        return None


def _parse_vtt_transcript(vtt_text: str) -> str:
    """
    Convert VTT subtitle format into clean readable plain text.

    VTT format:
        WEBVTT

        00:00:01.000 --> 00:00:04.000
        Speaker Name: What they said.

    Output: clean dialogue with speaker labels preserved.
    """
    lines = vtt_text.split("\n")
    result = []

    for line in lines:
        line = line.strip()
        if not line or line == "WEBVTT" or re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}[:\.]", line):
            continue
        line = re.sub(r"<v\s+([^>]+)>", r"\1: ", line)
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            result.append(line)

    # Deduplicate consecutive identical lines
    deduped = []
    prev = None
    for line in result:
        if line != prev:
            deduped.append(line)
            prev = line

    return "\n".join(deduped)


def convert_time(time_slot: str) -> str:
    """Convert '9:00 AM' to '09:00:00' for Zoom API."""
    from datetime import datetime

    t = datetime.strptime(time_slot, "%I:%M %p")
    return t.strftime("%H:%M:%S")


# ── Legacy alias ─────────────────────────────────────────────────────────────
def get_meeting_summary(meeting_uuid: str) -> str | None:
    """Legacy alias for get_meeting_data(). Use get_meeting_data() for new code."""
    data = get_meeting_data(meeting_uuid)
    return data.get("summary")
