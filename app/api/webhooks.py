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
from app.models.webhook_log import WebhookLog
from app.services.zoom import (
    get_meeting_data,
    get_meeting_transcript,
    download_recording_file,
)
from app.services.embedding_service import embed_booking_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _log_webhook(
    db: Session,
    event: str,
    raw_payload: dict,
    meeting_id: str = "",
    meeting_uuid: str = "",
    booking_found: str = "n/a",
    result: str = "ok",
) -> None:
    """
    Persist a webhook event to the webhook_logs table.
    Called for every Zoom event — before processing so failures
    during processing don't prevent the log entry from being saved.
    """
    try:
        log = WebhookLog(
            event=event,
            meeting_id=meeting_id or None,
            meeting_uuid=meeting_uuid or None,
            raw_payload=json.dumps(raw_payload, indent=2),
            booking_found=booking_found,
            result=result,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        # Never let logging failures break the webhook response
        logger.error(f"Failed to write webhook log: {e}")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/zoom")
async def zoom_webhook(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "unknown")

    # ── Log every raw payload immediately ───────────────────────────────
    # This runs before any processing so we always have a record of
    # what Zoom sent, even if the handler below crashes or silently skips.
    logger.info(
        f"[ZOOM WEBHOOK] event={event} | "
        f"payload_keys={list(payload.get('payload', {}).get('object', {}).keys())}"
    )

    # ── URL Validation Challenge ─────────────────────────────────────────
    if event == "endpoint.url_validation":
        plain_token = payload.get("payload", {}).get("plainToken", "")
        encrypted = hmac.new(
            settings.ZOOM_SECRET_TOKEN.encode("utf-8"),
            plain_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        logger.info("Zoom URL validation challenge answered.")
        # Don't log validation challenges to DB — they're noise
        return {"plainToken": plain_token, "encryptedToken": encrypted}

    # ── Signature verification ───────────────────────────────────────────
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    signature = request.headers.get("x-zm-signature", "")

    try:
        if abs(time.time() - int(timestamp)) > 300:
            _log_webhook(db, event, payload, result="rejected: timestamp too old")
            raise HTTPException(status_code=400, detail="Request timestamp too old")
    except (ValueError, TypeError):
        _log_webhook(db, event, payload, result="rejected: invalid timestamp")
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    if not _verify_zoom_signature(body_bytes, timestamp, signature):
        logger.warning("Zoom webhook signature verification failed")
        _log_webhook(db, event, payload, result="rejected: signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── Extract common identifiers for logging ───────────────────────────
    object_data = payload.get("payload", {}).get("object", {})
    meeting_id = str(object_data.get("id", ""))
    meeting_uuid = object_data.get("uuid", "")

    # ── meeting.ended — fetch AI summary only ────────────────────────────
    # Transcript is NOT attempted here. Cloud recording takes 5–15 minutes
    # to process after the meeting ends. recording.completed fires when
    # the files are actually ready — that's where we capture the transcript.
    if event == "meeting.ended":
        logger.info(f"[meeting.ended] id={meeting_id} uuid={meeting_uuid}")

        if not meeting_uuid:
            logger.warning("[meeting.ended] No UUID in payload")
            _log_webhook(db, event, payload, meeting_id=meeting_id, result="no uuid")
            return {"status": "ok", "reason": "no uuid"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )
        booking_found = "yes" if booking else "no"

        if not booking:
            logger.warning(
                f"[meeting.ended] No booking found for meeting_id={meeting_id}"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="no",
                result="no matching booking",
            )
            return {"status": "ok", "reason": "no matching booking"}

        meeting_data = get_meeting_data(meeting_uuid)
        result_notes = []

        if meeting_data:
            if meeting_data.get("summary"):
                booking.meeting_summary = meeting_data["summary"]
                result_notes.append("summary saved")
                logger.info(f"[meeting.ended] Summary saved for booking {booking.id}")
            if meeting_data.get("next_steps"):
                booking.meeting_next_steps = meeting_data["next_steps"]
                result_notes.append("next_steps saved")
            if meeting_data.get("keywords"):
                booking.meeting_keywords = meeting_data["keywords"]
                result_notes.append("keywords saved")
        else:
            result_notes.append("no AI Companion summary yet")
            logger.info(
                f"[meeting.ended] No AI Companion summary for meeting {meeting_id} "
                "— will update on meeting.summary_updated"
            )

        db.commit()
        _log_webhook(
            db,
            event,
            payload,
            meeting_id=meeting_id,
            meeting_uuid=meeting_uuid,
            booking_found=booking_found,
            result=", ".join(result_notes) or "ok",
        )
        return {"status": "ok"}

    # ── recording.completed — transcript is now ready ────────────────────
    # This fires 5–15 minutes after the meeting ends once Zoom finishes
    # processing the cloud recording. The payload contains download URLs
    # for every file type (MP4, M4A, TRANSCRIPT, CHAT) plus a download_token
    # valid for 24 hours. We use that token directly instead of fetching a
    # fresh OAuth token — it's already scoped to these specific files.
    if event == "recording.completed":
        download_token = object_data.get("download_token", "")
        recording_files = object_data.get("recording_files", [])

        # Log every file type we received — critical for debugging
        file_summary = [
            {
                "file_type": f.get("file_type"),
                "recording_type": f.get("recording_type"),
                "status": f.get("status"),
                "file_size": f.get("file_size"),
            }
            for f in recording_files
        ]
        logger.info(
            f"[recording.completed] id={meeting_id} | "
            f"download_token={'YES' if download_token else 'MISSING'} | "
            f"files={file_summary}"
        )

        if not meeting_id:
            _log_webhook(db, event, payload, result="no meeting id")
            return {"status": "ok", "reason": "no meeting id"}

        booking = (
            db.query(Booking).filter(Booking.meeting_url.contains(meeting_id)).first()
        )

        if not booking:
            logger.warning(
                f"[recording.completed] No booking found for meeting_id={meeting_id}"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="no",
                result="no matching booking",
            )
            return {"status": "ok", "reason": "no matching booking"}

        # Find the TRANSCRIPT file in the recording list
        transcript_url = None
        for f in recording_files:
            file_type = f.get("file_type", "").upper()
            recording_type = f.get("recording_type", "")
            file_status = f.get("status", "")

            if file_type == "TRANSCRIPT" or recording_type == "audio_transcript":
                if file_status in ("completed", ""):
                    transcript_url = f.get("download_url")
                    logger.info(
                        f"[recording.completed] TRANSCRIPT file found — "
                        f"status='{file_status}' url={transcript_url[:60] if transcript_url else 'None'}…"
                    )
                    break
                else:
                    logger.warning(
                        f"[recording.completed] TRANSCRIPT file found but status='{file_status}' "
                        f"for meeting {meeting_id} — skipping"
                    )

        if not transcript_url:
            logger.warning(
                f"[recording.completed] No TRANSCRIPT file in payload for meeting {meeting_id}. "
                f"File types received: {[f.get('file_type') for f in recording_files]}. "
                "Check: (1) Is Audio Transcript enabled in Zoom account settings? "
                "(2) Was there enough speech in the call?"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="yes",
                result=f"no transcript file — files present: {[f.get('file_type') for f in recording_files]}",
            )
            return {"status": "ok", "reason": "no transcript file"}

        if not download_token:
            logger.warning(
                f"[recording.completed] No download_token for meeting {meeting_id} "
                "— falling back to OAuth token fetch"
            )
            transcript = get_meeting_transcript(meeting_id)
        else:
            transcript = download_recording_file(transcript_url, download_token)

        if transcript:
            booking.meeting_transcript = transcript
            db.commit()
            background_tasks.add_task(embed_booking_background, booking.id)
            logger.info(
                f"[recording.completed] Transcript saved for booking {booking.id}: "
                f"{len(transcript)} chars"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="yes",
                result=f"transcript saved: {len(transcript)} chars",
            )
        else:
            logger.warning(
                f"[recording.completed] Transcript download returned empty for meeting {meeting_id}. "
                "Check the download_token and URL validity."
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="yes",
                result="transcript download returned empty",
            )

        return {"status": "ok"}

    # ── meeting.summary_updated — summary refresh ────────────────────────
    # Good safety net if the meeting.ended summary was empty.
    if event == "meeting.summary_updated":
        summary = object_data.get("summary", {})

        if isinstance(summary, dict):
            summary_text = summary.get("summary_overview") or summary.get("summary", "")
        else:
            summary_text = str(summary)

        if not meeting_id or not summary_text:
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                result="ignored: missing data",
            )
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
            logger.info(
                f"[meeting.summary_updated] Booking {booking.id} summary refreshed"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="yes",
                result="summary refreshed",
            )
        else:
            logger.warning(
                f"[meeting.summary_updated] No booking for meeting_id={meeting_id}"
            )
            _log_webhook(
                db,
                event,
                payload,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                booking_found="no",
                result="no matching booking",
            )

        return {"status": "ok"}

    # ── Unhandled event — log it so we know it arrived ───────────────────
    logger.info(f"[ZOOM WEBHOOK] Unhandled event: {event}")
    _log_webhook(
        db,
        event,
        payload,
        meeting_id=meeting_id,
        meeting_uuid=meeting_uuid,
        result="unhandled event",
    )
    return {"status": "ignored"}
