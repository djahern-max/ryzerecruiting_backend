# app/services/notifications.py
import logging
from app.core.config import settings
from app.services.email import (
    send_booking_received_email,
    send_meeting_confirmed,
    send_cancellation_email,
    send_reminder_email,
    send_recruiter_invite_with_response,
    send_invite_admin_copy,
    send_invite_accepted_confirmation,
    send_invite_accepted_admin_notify,
    send_invite_declined_admin_notify,
    send_candidate_booking_confirmation,
    send_candidate_confirmed_email,
    send_candidate_booking_admin_notify,
)

logger = logging.getLogger(__name__)


def _send_sms(to_phone: str, body: str) -> None:
    """Send SMS via Twilio. Silently skips if phone is blank or Twilio unavailable."""
    if not to_phone:
        return
    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=body,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_phone,
        )
    except Exception as e:
        logger.error(f"SMS failed to {to_phone}: {e}")


# ---------------------------------------------------------------------------
# Inbound employer — booking received (pending, awaiting admin confirmation)
# ---------------------------------------------------------------------------


def notify_booking_received(
    employer_name: str,
    email: str,
    phone: str,
    company_name: str,
    website_url: str,
    date: str,
    time_slot: str,
    notes: str = "",
) -> None:
    try:
        send_booking_received_email(
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
        logger.error(f"notify_booking_received — email failed: {e}")

    _send_sms(
        to_phone=phone,
        body=(
            f"Hi {employer_name}, RYZE.ai received your call request for "
            f"{date} at {time_slot} EST. "
            f"We will confirm shortly. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Inbound employer — booking confirmed
# ---------------------------------------------------------------------------


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
            f"Your call with RYZE.ai is confirmed for {date} at {time_slot} EST. "
            f"Your Zoom link has been sent to your email. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Inbound employer — booking cancelled
# ---------------------------------------------------------------------------


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
            f"Your RYZE.ai call scheduled for {date} at {time_slot} "
            f"has been cancelled. Visit ryze.ai to rebook. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Scheduler — 15-minute reminder
# ---------------------------------------------------------------------------


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
            f"Reminder: Your call with RYZE.ai is in 15 minutes. "
            f"Check your email for the Zoom link. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Outbound invite — sent to contact (email + admin copy + SMS)
# ---------------------------------------------------------------------------


def notify_recruiter_invite_sent(
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    invite_type: str,
    company_name: str,
    date: str,
    time_slot: str,
    booking_id: int,
    response_token: str,
    notes: str = "",
) -> None:
    contact_type = "employer" if invite_type == "outbound_employer" else "candidate"

    try:
        send_recruiter_invite_with_response(
            contact_name=contact_name,
            contact_email=contact_email,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            booking_id=booking_id,
            response_token=response_token,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"notify_recruiter_invite_sent — contact email failed: {e}")

    try:
        send_invite_admin_copy(
            contact_name=contact_name,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
        )
    except Exception as e:
        logger.error(f"notify_recruiter_invite_sent — admin copy failed: {e}")

    _send_sms(
        to_phone=contact_phone,
        body=(
            f"Hi {contact_name}, Dane from RYZE.ai sent you a meeting invite "
            f"for {date} at {time_slot} EST. "
            f"Check your email to accept or decline. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Outbound invite — accepted by contact (confirmation to contact)
# ---------------------------------------------------------------------------


def notify_invite_accepted(
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    invite_type: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    contact_type = "employer" if invite_type == "outbound_employer" else "candidate"

    try:
        send_invite_accepted_confirmation(
            contact_name=contact_name,
            contact_email=contact_email,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"notify_invite_accepted — confirmation email failed: {e}")

    _send_sms(
        to_phone=contact_phone,
        body=(
            f"Hi {contact_name}, your call with RYZE.ai is confirmed for "
            f"{date} at {time_slot} EST. "
            f"Zoom: {meeting_url} — Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Outbound invite — accepted: notify RECRUITER (new — fixes missing email bug)
# ---------------------------------------------------------------------------


def notify_invite_accepted_admin(
    contact_name: str,
    contact_type: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    """
    Fires when an outbound invite is accepted by the contact.
    Sends a confirmation email to ADMIN_EMAIL so the recruiter knows the call is locked in.
    """
    try:
        send_invite_accepted_admin_notify(
            contact_name=contact_name,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"notify_invite_accepted_admin — admin email failed: {e}")


# ---------------------------------------------------------------------------
# Outbound invite — declined by contact
# ---------------------------------------------------------------------------


def notify_invite_declined(
    contact_name: str,
    contact_email: str,
    invite_type: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    contact_type = "employer" if invite_type == "outbound_employer" else "candidate"

    try:
        send_invite_declined_admin_notify(
            contact_name=contact_name,
            contact_type=contact_type,
            company_name=company_name,
            date=date,
            time_slot=time_slot,
        )
    except Exception as e:
        logger.error(f"notify_invite_declined — admin email failed: {e}")


# ---------------------------------------------------------------------------
# Candidate — self-booking received
# ---------------------------------------------------------------------------


def notify_candidate_booking_received(
    candidate_name: str,
    email: str,
    phone: str,
    date: str,
    time_slot: str,
    notes: str = "",
) -> None:
    try:
        send_candidate_booking_admin_notify(
            candidate_name=candidate_name,
            candidate_email=email,
            phone=phone,
            date=date,
            time_slot=time_slot,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"notify_candidate_booking_received — admin email failed: {e}")

    try:
        send_candidate_booking_confirmation(
            candidate_name=candidate_name,
            candidate_email=email,
            date=date,
            time_slot=time_slot,
        )
    except Exception as e:
        logger.error(f"notify_candidate_booking_received — candidate email failed: {e}")

    _send_sms(
        to_phone=phone,
        body=(
            f"Hi {candidate_name}, RYZE.ai received your call request for "
            f"{date} at {time_slot} EST. We'll be in touch shortly. Reply STOP to opt out."
        ),
    )


# ---------------------------------------------------------------------------
# Candidate — confirmed by admin (Zoom link sent to candidate)
# ---------------------------------------------------------------------------


def notify_candidate_confirmed(
    candidate_name: str,
    email: str,
    phone: str,
    date: str,
    time_slot: str,
    meeting_url: str = "",
) -> None:
    try:
        send_candidate_confirmed_email(
            candidate_name=candidate_name,
            candidate_email=email,
            date=date,
            time_slot=time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"notify_candidate_confirmed — email failed: {e}")

    _send_sms(
        to_phone=phone,
        body=(
            f"Hi {candidate_name}, your call with RYZE.ai is confirmed for "
            f"{date} at {time_slot} EST. "
            f"Zoom link is in your email. Reply STOP to opt out."
        ),
    )
