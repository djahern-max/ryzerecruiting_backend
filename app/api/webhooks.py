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
from app.services.zoom import get_meeting_summary
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

    # ── meeting.ended — fetch summary using UUID ─────────────────────────
    if event == "meeting.ended":
        object_data = payload.get("payload", {}).get("object", {})
        meeting_id = str(object_data.get("id", ""))
        meeting_uuid = object_data.get("uuid", "")

        logger.info(f"meeting.ended — id: {meeting_id}, uuid: {meeting_uuid}")

        if not meeting_uuid:
            logger.warning("No UUID in meeting.ended payload")
            return {"status": "ok", "reason": "no uuid"}

        # Match booking by numeric meeting_id in the join URL
        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )

        if not booking:
            logger.warning(f"No booking found for meeting_id: {meeting_id}")
            return {"status": "ok", "reason": "no matching booking"}

        # Fetch summary using UUID
        summary_text = get_meeting_summary(meeting_uuid)

        if summary_text:
            booking.meeting_summary = summary_text
            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(f"Meeting summary saved for booking {booking.id}")
        else:
            logger.info(
                f"No summary available for meeting {meeting_id} — AI Companion may not have been active"
            )

        return {"status": "ok"}

    # ── meeting.summary_updated (fallback) ───────────────────────────────
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
            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(
                f"Summary saved via summary_updated event for booking {booking.id}"
            )

        return {"status": "ok"}

    logger.info(f"Unhandled Zoom webhook event: {event}")
    return {"status": "ignored"}
