# app/api/webhooks.py
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends

from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking
from app.services.zoom import get_meeting_data, get_meeting_transcript
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

    # ── meeting.ended — fetch rich summary + transcript ──────────────────
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

        # ── Fetch rich AI Companion summary data ─────────────────────────
        meeting_data = get_meeting_data(meeting_uuid)
        if meeting_data:
            if meeting_data.get("summary"):
                booking.meeting_summary = meeting_data["summary"]
                logger.info(f"Summary saved for booking {booking.id}")
            if meeting_data.get("next_steps"):
                booking.meeting_next_steps = meeting_data["next_steps"]
                logger.info(f"Next steps saved for booking {booking.id}")
            if meeting_data.get("keywords"):
                booking.meeting_keywords = meeting_data["keywords"]
                logger.info(f"Keywords saved for booking {booking.id}")
        else:
            logger.info(
                f"No AI Companion summary available for meeting {meeting_id} — "
                "AI Companion may not have been active"
            )

        # ── Fetch transcript ─────────────────────────────────────────────
        # Note: Zoom transcripts take 1-5 minutes to process after meeting ends.
        # We attempt fetch immediately — if None is returned that is expected
        # for the very first webhook fire. The summary_updated event below
        # provides a second opportunity to capture it.
        transcript = get_meeting_transcript(meeting_id)
        if transcript:
            booking.meeting_transcript = transcript
            logger.info(
                f"Transcript saved for booking {booking.id}: {len(transcript)} chars"
            )
        else:
            logger.info(
                f"Transcript not yet available for meeting {meeting_id} — "
                "will retry on summary_updated event"
            )

        db.commit()
        background_tasks.add_task(embed_booking_background, booking.id)
        return {"status": "ok"}

    # ── meeting.summary_updated — fallback / transcript retry ────────────
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
            # Update summary
            booking.meeting_summary = summary_text

            # Try to extract next_steps / keywords if summary is a dict
            if isinstance(summary, dict):
                raw_next_steps = summary.get("next_steps", [])
                if isinstance(raw_next_steps, list) and raw_next_steps:
                    booking.meeting_next_steps = "\n".join(
                        f"• {s}" for s in raw_next_steps if s
                    )
                raw_keywords = summary.get("keywords", [])
                if isinstance(raw_keywords, list) and raw_keywords:
                    booking.meeting_keywords = ", ".join(str(k) for k in raw_keywords)

            # Retry transcript fetch — may now be ready since summary_updated
            # fires a few minutes after meeting.ended
            if not booking.meeting_transcript:
                transcript = get_meeting_transcript(meeting_id)
                if transcript:
                    booking.meeting_transcript = transcript
                    logger.info(
                        f"Transcript saved on summary_updated for booking {booking.id}: "
                        f"{len(transcript)} chars"
                    )

            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(f"Booking {booking.id} updated on summary_updated event")

        return {"status": "ok"}

    logger.info(f"Unhandled Zoom webhook event: {event}")
    return {"status": "ignored"}
