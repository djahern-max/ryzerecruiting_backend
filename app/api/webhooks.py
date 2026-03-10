# app/api/webhooks.py
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_zoom_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify Zoom webhook signature.
    Zoom signs payloads as: v0={HMAC-SHA256 of "v0:{timestamp}:{body}"}
    """
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
async def zoom_webhook(request: Request, db: Session = Depends(get_db)):
    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")

    # ── URL Validation Challenge (Zoom fires this when you first save the endpoint) ──
    if event == "endpoint.url_validation":
        plain_token = payload.get("payload", {}).get("plainToken", "")
        encrypted = hmac.new(
            settings.ZOOM_SECRET_TOKEN.encode("utf-8"),
            plain_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        logger.info("Zoom URL validation challenge received and answered.")
        return {"plainToken": plain_token, "encryptedToken": encrypted}

    # ── Signature verification for all real events ──────────────────────
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    signature = request.headers.get("x-zm-signature", "")

    # Reject stale requests (>5 min old)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=400, detail="Request timestamp too old")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    if not _verify_zoom_signature(body_bytes, timestamp, signature):
        logger.warning("Zoom webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── meeting.summary_completed ────────────────────────────────────────
    if event == "meeting.summary_completed":
        meeting_payload = payload.get("payload", {})
        object_data = meeting_payload.get("object", {})
        meeting_id = str(object_data.get("id", ""))
        summary = object_data.get("summary", {})

        # Zoom sends summary as either a plain string or a nested object
        if isinstance(summary, dict):
            summary_text = summary.get("summary_overview") or summary.get("summary", "")
        else:
            summary_text = str(summary)

        if not meeting_id or not summary_text:
            logger.warning(f"meeting.summary_completed missing data: id={meeting_id}")
            return {"status": "ignored", "reason": "missing meeting_id or summary"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )

        if not booking:
            logger.warning(f"No booking found for Zoom meeting_id: {meeting_id}")
            return {"status": "ignored", "reason": "no matching booking"}

        booking.meeting_summary = summary_text
        db.commit()
        logger.info(
            f"Meeting summary saved for booking {booking.id} (meeting {meeting_id})"
        )
        return {"status": "ok"}

    # ── meeting.ended (log only — summary arrives via summary_completed) ─
    if event == "meeting.ended":
        object_data = payload.get("payload", {}).get("object", {})
        meeting_id = str(object_data.get("id", ""))
        logger.info(f"meeting.ended received for meeting_id: {meeting_id}")
        return {"status": "ok"}

    # ── Unknown events ───────────────────────────────────────────────────
    logger.info(f"Unhandled Zoom webhook event: {event}")
    return {"status": "ignored"}
