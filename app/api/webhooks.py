# app/api/webhooks.py
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking
from app.services.zoom import (
    get_meeting_data,
    get_meeting_transcript,
    download_recording_file,
)
from app.services.embedding_service import embed_booking_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_zoom_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    message = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            settings.ZOOM_SECRET_TOKEN.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.post("/zoom")
async def zoom_webhook(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")

    # ── URL Validation Challenge ─────────────────────────────────────────
    if event == "endpoint.url_validation":
        plain_token = payload.get("payload", {}).get("plainToken", "")
        encrypted = hmac.new(
            settings.ZOOM_SECRET_TOKEN.encode("utf-8"),
            plain_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        logger.info("Zoom URL validation challenge answered.")
        return {"plainToken": plain_token, "encryptedToken": encrypted}

    # ── Signature verification ───────────────────────────────────────────
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    signature = request.headers.get("x-zm-signature", "")

    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=400, detail="Request timestamp too old")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    if not _verify_zoom_signature(body_bytes, timestamp, signature):
        logger.warning("Zoom webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── meeting.ended — fetch AI summary only ────────────────────────────
    # Transcript is NOT attempted here. Cloud recording takes 5–15 minutes
    # to process after the meeting ends. recording.completed fires when
    # the files are actually ready — that's where we capture the transcript.
    if event == "meeting.ended":
        object_data = payload.get("payload", {}).get("object", {})
        meeting_id = str(object_data.get("id", ""))
        meeting_uuid = object_data.get("uuid", "")

        logger.info(f"meeting.ended — id: {meeting_id}, uuid: {meeting_uuid}")

        if not meeting_uuid:
            logger.warning("No UUID in meeting.ended payload")
            return {"status": "ok", "reason": "no uuid"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )
        if not booking:
            logger.warning(f"No booking found for meeting_id: {meeting_id}")
            return {"status": "ok", "reason": "no matching booking"}

        meeting_data = get_meeting_data(meeting_uuid)
        if meeting_data:
            if meeting_data.get("summary"):
                booking.meeting_summary = meeting_data["summary"]
                logger.info(f"Summary saved for booking {booking.id}")
            if meeting_data.get("next_steps"):
                booking.meeting_next_steps = meeting_data["next_steps"]
            if meeting_data.get("keywords"):
                booking.meeting_keywords = meeting_data["keywords"]
        else:
            logger.info(
                f"No AI Companion summary yet for meeting {meeting_id} — "
                "will update on meeting.summary_updated"
            )

        db.commit()
        return {"status": "ok"}

    # ── recording.completed — transcript is now ready ────────────────────
    # This fires 5–15 minutes after the meeting ends once Zoom finishes
    # processing the cloud recording. The payload contains download URLs
    # for every file type (MP4, M4A, TRANSCRIPT, CHAT) plus a download_token
    # valid for 24 hours. We use that token directly instead of fetching a
    # fresh OAuth token — it's already scoped to these specific files.
    if event == "recording.completed":
        object_data = payload.get("payload", {}).get("object", {})
        meeting_id = str(object_data.get("id", ""))
        download_token = object_data.get("download_token", "")
        recording_files = object_data.get("recording_files", [])

        logger.info(
            f"recording.completed — id: {meeting_id}, "
            f"files: {[f.get('file_type') for f in recording_files]}"
        )

        if not meeting_id:
            return {"status": "ok", "reason": "no meeting id"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )
        if not booking:
            logger.warning(f"No booking found for meeting_id: {meeting_id}")
            return {"status": "ok", "reason": "no matching booking"}

        # Find the TRANSCRIPT file in the recording list
        transcript_url = None
        for f in recording_files:
            file_type = f.get("file_type", "").upper()
            recording_type = f.get("recording_type", "")
            file_status = f.get("status", "")

            if file_type == "TRANSCRIPT" or recording_type == "audio_transcript":
                # Only download if file is fully processed
                if file_status in ("completed", ""):
                    transcript_url = f.get("download_url")
                    break
                else:
                    logger.info(
                        f"Transcript file found but status is '{file_status}' "
                        f"for meeting {meeting_id} — skipping"
                    )

        if not transcript_url:
            logger.info(
                f"No TRANSCRIPT file in recording.completed for meeting {meeting_id}"
            )
            return {"status": "ok", "reason": "no transcript file"}

        if not download_token:
            logger.warning(
                f"recording.completed has no download_token for meeting {meeting_id} "
                "— falling back to OAuth token fetch"
            )
            # Fallback: poll the recordings API (slower but works)
            transcript = get_meeting_transcript(meeting_id)
        else:
            transcript = download_recording_file(transcript_url, download_token)

        if transcript:
            booking.meeting_transcript = transcript
            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(
                f"Transcript saved for booking {booking.id}: {len(transcript)} chars"
            )
        else:
            logger.warning(
                f"Transcript download returned empty for meeting {meeting_id}"
            )

        return {"status": "ok"}

    # ── meeting.summary_updated — summary refresh + transcript fallback ──
    # Fires a few minutes after meeting.ended. Good safety net if the
    # meeting.ended summary was empty (AI Companion sometimes takes longer).
    if event == "meeting.summary_updated":
        object_data = payload.get("payload", {}).get("object", {})
        meeting_id = str(object_data.get("id", ""))
        summary = object_data.get("summary", {})

        if isinstance(summary, dict):
            summary_text = summary.get("summary_overview") or summary.get("summary", "")
        else:
            summary_text = str(summary)

        if not meeting_id or not summary_text:
            return {"status": "ignored", "reason": "missing data"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )
        if booking:
            booking.meeting_summary = summary_text

            if isinstance(summary, dict):
                raw_next_steps = summary.get("next_steps", [])
                if isinstance(raw_next_steps, list) and raw_next_steps:
                    booking.meeting_next_steps = "\n".join(
                        f"• {s}" for s in raw_next_steps if s
                    )
                raw_keywords = summary.get("keywords", [])
                if isinstance(raw_keywords, list) and raw_keywords:
                    booking.meeting_keywords = ", ".join(str(k) for k in raw_keywords)

            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(f"Booking {booking.id} summary refreshed on summary_updated")

        return {"status": "ok"}

    logger.info(f"Unhandled Zoom webhook event: {event}")
    return {"status": "ignored"}
