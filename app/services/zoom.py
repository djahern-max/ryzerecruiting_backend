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
            "auto_recording": "cloud",  # enables cloud recording for transcript
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
    All values are strings; missing fields return None.
    """
    try:
        token = get_access_token()

        # Double-encode UUIDs that contain '/' or '//'
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
        # Zoom returns next_steps as a list of dicts or strings
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


def get_meeting_transcript(meeting_id: str) -> str | None:
    """
    Fetch the cloud recording transcript for a completed meeting.
    Returns the full transcript as plain text, or None if unavailable.

    Requires cloud recording + audio transcript enabled in Zoom settings.
    Zoom transcripts take 1-5 minutes to process after the meeting ends —
    if None is returned immediately after meeting.ended, that is expected.
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

        # Find the transcript file (TRANSCRIPT type or audio_transcript recording type)
        transcript_url = None
        for file in recording_files:
            file_type = file.get("file_type", "").upper()
            recording_type = file.get("recording_type", "")
            if file_type == "TRANSCRIPT" or recording_type == "audio_transcript":
                transcript_url = file.get("download_url")
                break

        if not transcript_url:
            logger.info(
                f"No transcript file found in recordings for meeting {meeting_id}"
            )
            return None

        # Download the VTT transcript (requires access token as query param)
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
        # Skip header, blank lines, numeric cue identifiers
        if not line or line == "WEBVTT" or re.match(r"^\d+$", line):
            continue
        # Skip timestamp lines (00:00:00.000 --> 00:00:00.000)
        if re.match(r"^\d{2}:\d{2}[:\.]", line):
            continue
        # Convert <v Speaker> VTT tags to "Speaker: "
        line = re.sub(r"<v\s+([^>]+)>", r"\1: ", line)
        # Strip any remaining VTT/HTML tags
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            result.append(line)

    # Deduplicate consecutive identical lines (VTT sometimes repeats lines)
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


# ---------------------------------------------------------------------------
# Legacy alias — keeps any existing callers working
# ---------------------------------------------------------------------------


def get_meeting_summary(meeting_uuid: str) -> str | None:
    """Legacy alias for get_meeting_data(). Use get_meeting_data() for new code."""
    data = get_meeting_data(meeting_uuid)
    return data.get("summary")
