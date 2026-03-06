# app/services/notifications.py
import logging
from app.core.config import settings
from app.services.email import (
    send_employer_confirmation,
    send_admin_notification,
    send_meeting_confirmed,
    send_cancellation_email,
    send_reminder_email,
    send_recruiter_invite,          # new — add this to email.py
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

    digits = "".join(filter(str.isdigit, to_phone))
    if len(digits) == 10:
        digits = "1" + digits
    if not digits.startswith("1") or len(digits) != 11:
        logger.warning(f"SMS skipped — invalid phone format: {to_phone}")
        return
    normalized = "+" + digits

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_FROM_NUMBER,
            to=normalized,
        )
        logger.info(f"SMS sent to {normalized} — SID: {message.sid}")
    except Exception as e:
        logger.error(f"SMS failed to {normalized}: {e}")


# ---------------------------------------------------------------------------
# Inbound booking notifications (existing flows — unchanged)
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
    meeting_url: str = "",
) -> None:
    try:
        send_reminder_email(
            employer_name=employer_name,
            employer_email=email,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"notify_reminder — employer email failed: {e}")

    try:
        send_reminder_email(
            employer_name=employer_name,
            employer_email=settings.ADMIN_EMAIL,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"notify_reminder — admin email failed: {e}")

    _send_sms(
        to_phone=phone,
        body=(
            f"Reminder: Your call with RYZE Recruiting is in 15 minutes. "
            f"Check your email for the Zoom link. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Outbound invite notification (new — recruiter-initiated)
# ---------------------------------------------------------------------------


def notify_recruiter_invite_sent(
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    invite_type: str,           # "outbound_employer" | "outbound_candidate"
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
    notes: str = "",
    ai_brief: dict = None,
) -> None:
    """
    Fire when the recruiter sends an outbound meeting invite.
    - Sends invite email to the contact with the Zoom link
    - Sends admin copy to the recruiter
    - Fires SMS if phone is present
    """

    contact_type = "employer" if invite_type == "outbound_employer" else "candidate"

    # Email to contact
    try:
        send_recruiter_invite(
            contact_name=contact_name,
            contact_email=contact_email,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"notify_recruiter_invite_sent — contact email failed: {e}")

    # Admin copy
    try:
        send_recruiter_invite(
            contact_name=contact_name,
            contact_email=settings.ADMIN_EMAIL,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
            notes=notes,
            is_admin_copy=True,
        )
    except Exception as e:
        logger.error(f"notify_recruiter_invite_sent — admin copy failed: {e}")

    # SMS to contact
    _send_sms(
        to_phone=contact_phone,
        body=(
            f"Hi {contact_name}, Dane from RYZE Recruiting has scheduled a call "
            f"with you on {date} at {time_slot} EST. "
            f"Check your email for the Zoom link. Reply STOP to opt out."
        ),
    )
