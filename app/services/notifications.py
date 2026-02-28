# app/services/notifications.py
import logging
from app.core.config import settings
from app.services.email import (
    send_employer_confirmation,
    send_admin_notification,
    send_meeting_confirmed,
    send_cancellation_email,
)

logger = logging.getLogger(__name__)


def _send_sms(to_phone: str, body: str) -> None:
    """Send an SMS via Twilio. Skips silently if phone is missing or Twilio is not configured."""
    if not to_phone or not to_phone.strip():
        logger.info("SMS skipped — no phone number provided.")
        return

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info("SMS skipped — Twilio credentials not configured.")
        return

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_phone,
        )
        logger.info(f"SMS sent to {to_phone} — SID: {message.sid}")
    except Exception as e:
        logger.error(f"SMS failed to {to_phone}: {e}")


# ---------------------------------------------------------------------------
# Public notification functions
# ---------------------------------------------------------------------------


def notify_booking_received(
    employer_name: str,
    email: str,
    phone: str,
    company_name: str,
    date: str,
    time_slot: str,
    website_url: str = "",
    notes: str = "",
) -> None:
    """Fire when a new booking is submitted — confirms receipt to employer, alerts admin."""

    # Email
    try:
        send_employer_confirmation(
            employer_name=employer_name,
            employer_email=email,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
        )
    except Exception as e:
        logger.error(f"notify_booking_received — email failed: {e}")

    try:
        send_admin_notification(
            employer_name=employer_name,
            employer_email=email,
            company_name=company_name,
            website_url=website_url,
            date=date,
            time_slot=time_slot,
            phone=phone,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"notify_booking_received — admin email failed: {e}")

    # SMS
    _send_sms(
        to_phone=phone,
        body=(
            f"Hi {employer_name}, RYZE Recruiting received your call request "
            f"for {date} at {time_slot}. We will confirm shortly."
        ),
    )


def notify_booking_confirmed(
    employer_name: str,
    email: str,
    phone: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
    notes: str = "",
    ai_brief: dict = None,
) -> None:
    """Fire when admin confirms a booking — sends Zoom link to employer, brief to admin."""

    # Email
    try:
        send_meeting_confirmed(
            employer_name=employer_name,
            employer_email=email,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
            phone=phone,
            notes=notes,
            ai_brief=ai_brief or {},
        )
    except Exception as e:
        logger.error(f"notify_booking_confirmed — email failed: {e}")

    # SMS
    _send_sms(
        to_phone=phone,
        body=(
            f"Your call with RYZE Recruiting is confirmed for {date} at {time_slot} EST. "
            f"Your Zoom link has been sent to your email."
        ),
    )


def notify_booking_cancelled(
    employer_name: str,
    email: str,
    phone: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Fire when a booking is cancelled — notifies employer by email and SMS."""

    # Email
    try:
        send_cancellation_email(
            employer_name=employer_name,
            employer_email=email,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
        )
    except Exception as e:
        logger.error(f"notify_booking_cancelled — email failed: {e}")

    # SMS
    _send_sms(
        to_phone=phone,
        body=(
            f"Your RYZE Recruiting call scheduled for {date} at {time_slot} "
            f"has been cancelled. Visit ryzerecruiting.com to rebook. Reply STOP to opt out."
        ),
    )


def notify_reminder(
    employer_name: str,
    email: str,
    phone: str,
    date: str,
    time_slot: str,
) -> None:
    """Fire 15 minutes before a confirmed call — used by Task 4 scheduler."""

    # SMS
    _send_sms(
        to_phone=phone,
        body=(
            f"Reminder: Your call with RYZE Recruiting is in 15 minutes. "
            f"Check your email for the Zoom link. Reply STOP to opt out."
        ),
    )
