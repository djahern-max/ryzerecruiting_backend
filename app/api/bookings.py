# app/api/bookings.py
from datetime import datetime
import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List

from app.services.ai_brief import generate_pre_call_brief
from app.services.calendar import create_calendar_event, delete_calendar_event
from app.core.config import settings
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.booking import Booking
from app.models.employer_profile import EmployerProfile
from app.models.user import User
from app.schemas.booking import (
    BookingCreate,
    BookingStatusUpdate,
    BookingResponse,
    RecruiterInviteCreate,
    CandidateBookingCreate,
)

from app.services.notifications import (
    notify_booking_received,
    notify_booking_confirmed,
    notify_booking_cancelled,
    notify_recruiter_invite_sent,
    notify_candidate_booking_received,
    notify_invite_accepted,
    notify_invite_declined,
)
from app.services.zoom import create_meeting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


# ---------------------------------------------------------------------------
# Employer endpoint — create a booking (inbound)
# ---------------------------------------------------------------------------


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = Booking(
        booking_type="inbound",
        employer_id=current_user.id,
        employer_name=current_user.full_name or current_user.email,
        employer_email=current_user.email,
        company_name=payload.company_name,
        website_url=payload.website_url,
        date=payload.date,
        time_slot=payload.time_slot,
        phone=payload.phone,
        notes=payload.notes,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    try:
        notify_booking_received(
            employer_name=current_user.full_name or current_user.email,
            email=current_user.email,
            phone=payload.phone or "",
            company_name=payload.company_name or "",
            website_url=payload.website_url or "",
            date=str(payload.date),
            time_slot=payload.time_slot,
            notes=payload.notes or "",
        )
    except Exception as e:
        logger.error(f"Failed to send booking received notifications: {e}")

    return booking


# ---------------------------------------------------------------------------
# Recruiter endpoint — send outbound meeting invite (NOW PENDING + TOKEN)
# ---------------------------------------------------------------------------


@router.post(
    "/recruiter-invite",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_recruiter_invite(
    payload: RecruiterInviteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Recruiter sends an outbound meeting invite to an employer contact or candidate.
    Booking is created as PENDING — no Zoom or Calendar until the contact accepts.
    A response_token is generated and embedded in Accept/Decline links in the email.
    """

    # 1. Generate a secure token for the Accept/Decline links
    token = secrets.token_urlsafe(32)

    # 2. Persist booking as PENDING (no Zoom yet)
    booking = Booking(
        booking_type=payload.invite_type,
        employer_id=None,
        employer_name=payload.contact_name,
        employer_email=payload.contact_email,
        company_name=payload.company_name,
        website_url=payload.website_url,
        date=payload.date,
        time_slot=payload.time_slot,
        phone=payload.contact_phone,
        notes=payload.notes,
        status="pending",
        response_token=token,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # 3. Send invite email with Accept/Decline links (no Zoom link yet)
    try:
        notify_recruiter_invite_sent(
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone or "",
            invite_type=payload.invite_type,
            company_name=payload.company_name or "",
            date=str(payload.date),
            time_slot=payload.time_slot,
            booking_id=booking.id,
            response_token=token,
            notes=payload.notes or "",
        )
    except Exception as e:
        logger.error(f"Failed to send recruiter invite notifications: {e}")

    return booking


# ---------------------------------------------------------------------------
# Public endpoint — candidate/employer responds to invite (no auth required)
# ---------------------------------------------------------------------------


@router.get("/respond", response_class=HTMLResponse)
def respond_to_invite(
    token: str = Query(...),
    action: str = Query(...),  # "accept" | "decline"
    db: Session = Depends(get_db),
):
    """
    Token-based accept/decline endpoint — no login required.
    Linked from the invite email buttons.
    On accept: creates Zoom + Calendar, flips to confirmed, sends confirmation.
    On decline: flips to cancelled, notifies admin.
    """

    # Validate token
    booking = db.query(Booking).filter(Booking.response_token == token).first()

    if not booking:
        return _response_page(
            "Invalid Link",
            "This link is no longer valid or has already been used.",
            success=False,
        )

    if booking.status != "pending":
        already = "accepted" if booking.status == "confirmed" else "declined"
        return _response_page(
            "Already Responded",
            f"You've already {already} this meeting request.",
            success=booking.status == "confirmed",
        )

    if action not in ("accept", "decline"):
        raise HTTPException(status_code=400, detail="Invalid action.")

    # ── ACCEPT ──────────────────────────────────────────────────────────
    if action == "accept":
        # Create Zoom meeting
        try:
            zoom = create_meeting(
                topic=f"RYZE Recruiting — {booking.company_name or booking.employer_name}",
                date=str(booking.date),
                time_slot=booking.time_slot,
            )
            booking.meeting_url = zoom["join_url"]
            logger.info(f"Zoom meeting created on accept: {zoom['meeting_id']}")
        except Exception as e:
            logger.error(f"Failed to create Zoom meeting on accept: {e}")
            return _response_page(
                "Something Went Wrong",
                "We couldn't set up the Zoom meeting. Please contact RYZE Recruiting directly.",
                success=False,
            )

        # Create Google Calendar event
        try:
            event_id = create_calendar_event(
                company_name=booking.company_name or "",
                employer_name=booking.employer_name,
                employer_email=booking.employer_email,
                date_str=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
            )
            if event_id:
                booking.calendar_event_id = event_id
        except Exception as e:
            logger.error(f"Failed to create Calendar event on accept: {e}")

        # Generate AI brief for employer invites
        if booking.booking_type == "outbound_employer" and booking.website_url:
            try:
                brief_dict = generate_pre_call_brief(booking.website_url)
                # Upsert employer profile
                profile = (
                    db.query(EmployerProfile)
                    .filter(EmployerProfile.website_url == booking.website_url)
                    .first()
                )
                if not profile:
                    profile = EmployerProfile(
                        website_url=booking.website_url,
                        company_name=booking.company_name or "",
                    )
                    db.add(profile)
                    db.flush()
                if brief_dict:
                    profile.ai_company_overview = brief_dict.get("company_overview")
                    profile.ai_industry = brief_dict.get("industry")
                    profile.ai_company_size = brief_dict.get("estimated_size")
                    profile.ai_hiring_needs = json.dumps(
                        brief_dict.get("hiring_needs", [])
                    )
                    profile.ai_talking_points = json.dumps(
                        brief_dict.get("talking_points", [])
                    )
                    profile.ai_red_flags = brief_dict.get("red_flags")
                    profile.ai_brief_updated_at = datetime.utcnow()
                booking.employer_profile_id = profile.id
                db.flush()  # catch any DB errors inside the try
            except Exception as e:
                logger.error(f"Failed to generate AI brief on accept: {e}")

        booking.status = "confirmed"
        booking.response_token = None
        db.commit()

        # Send confirmation with Zoom link
        try:
            notify_invite_accepted(
                contact_name=booking.employer_name,
                contact_email=booking.employer_email,
                contact_phone=booking.phone or "",
                invite_type=booking.booking_type,
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
            )
        except Exception as e:
            logger.error(f"Failed to send acceptance notifications: {e}")

        return _response_page(
            "You're Confirmed! 🎉",
            f"Your call with Dane at RYZE Recruiting is set for {booking.date.strftime('%B %d, %Y')} at {booking.time_slot} EST. Check your email for the Zoom link.",
            success=True,
            meeting_url=booking.meeting_url,
        )

    # ── DECLINE ─────────────────────────────────────────────────────────
    if action == "decline":
        booking.status = "cancelled"
        booking.response_token = None
        db.commit()

        try:
            notify_invite_declined(
                contact_name=booking.employer_name,
                contact_email=booking.employer_email,
                invite_type=booking.booking_type,
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
            )
        except Exception as e:
            logger.error(f"Failed to send decline notifications: {e}")

        return _response_page(
            "Got it — maybe next time.",
            "You've declined this meeting request. No worries — if you change your mind, reach out to RYZE Recruiting directly.",
            success=False,
            show_site_link=True,
        )


# ---------------------------------------------------------------------------
# Status update (admin PATCH — inbound flows)
# ---------------------------------------------------------------------------


@router.patch("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    is_candidate_booking = booking.booking_type in (
        "inbound_candidate",
        "outbound_candidate",
    )

    # ── Confirming ──────────────────────────────────────────────────────
    if payload.status == "confirmed" and booking.status != "confirmed":
        # Create Zoom meeting
        try:
            zoom = create_meeting(
                topic=f"RYZE Recruiting — {booking.company_name or booking.employer_name}",
                date=str(booking.date),
                time_slot=booking.time_slot,
            )
            booking.meeting_url = zoom["join_url"]
        except Exception as e:
            logger.error(f"Failed to create Zoom meeting: {e}")
            raise HTTPException(
                status_code=500, detail=f"Could not create Zoom meeting: {str(e)}"
            )

        # Create Google Calendar event
        try:
            event_id = create_calendar_event(
                company_name=booking.company_name or "",
                employer_name=booking.employer_name,
                employer_email=booking.employer_email,
                date_str=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
            )
            if event_id:
                booking.calendar_event_id = event_id
        except Exception as e:
            logger.error(f"Failed to create Calendar event: {e}")

        # AI brief (employer inbound only)
        brief_dict = {}
        if not is_candidate_booking and booking.website_url:
            try:
                brief_dict = generate_pre_call_brief(booking.website_url)
                profile = (
                    db.query(EmployerProfile)
                    .filter(EmployerProfile.id == booking.employer_profile_id)
                    .first()
                    if booking.employer_profile_id
                    else None
                )

                if not profile:
                    profile = EmployerProfile(
                        website_url=booking.website_url,
                        company_name=booking.company_name or "",
                    )
                    db.add(profile)
                    db.flush()

                if brief_dict:
                    profile.ai_company_overview = brief_dict.get("company_overview")
                    profile.ai_industry = brief_dict.get("industry")
                    profile.ai_company_size = brief_dict.get("estimated_size")
                    profile.ai_hiring_needs = json.dumps(
                        brief_dict.get("hiring_needs", [])
                    )
                    profile.ai_talking_points = json.dumps(
                        brief_dict.get("talking_points", [])
                    )
                    profile.ai_red_flags = brief_dict.get("red_flags")
                    profile.ai_brief_updated_at = datetime.utcnow()
                booking.employer_profile_id = profile.id
            except Exception as e:
                logger.error(f"Failed to generate AI brief: {e}")

        try:
            brief_dict_safe = brief_dict if isinstance(brief_dict, dict) else {}
            notify_booking_confirmed(
                employer_name=booking.employer_name,
                email=booking.employer_email,
                phone=booking.phone or "",
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
                notes=booking.notes or "",
                ai_brief=brief_dict_safe,
            )
        except Exception as e:
            logger.error(f"Failed to send booking confirmed notifications: {e}")

    # ── Cancelling ──────────────────────────────────────────────────────
    if payload.status == "cancelled" and booking.status != "cancelled":
        if booking.calendar_event_id:
            try:
                delete_calendar_event(booking.calendar_event_id)
                booking.calendar_event_id = None
            except Exception as e:
                logger.error(f"Failed to delete Google Calendar event: {e}")

        try:
            notify_booking_cancelled(
                employer_name=booking.employer_name,
                email=booking.employer_email,
                phone=booking.phone or "",
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
            )
        except Exception as e:
            logger.error(f"Failed to send booking cancelled notifications: {e}")

    booking.status = payload.status
    db.commit()
    db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    db.delete(booking)
    db.commit()


# ---------------------------------------------------------------------------
# Candidate endpoint — self-book a call (inbound_candidate)
# ---------------------------------------------------------------------------


@router.post(
    "/candidate",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate_booking(
    payload: CandidateBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = Booking(
        booking_type="inbound_candidate",
        employer_id=current_user.id,
        employer_name=payload.name,
        employer_email=current_user.email,
        company_name=payload.company_name,
        date=payload.date,
        time_slot=payload.time_slot,
        phone=payload.phone,
        notes=payload.notes,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    try:
        notify_candidate_booking_received(
            candidate_name=payload.name,
            email=current_user.email,
            phone=payload.phone or "",
            date=str(payload.date),
            time_slot=payload.time_slot,
            notes=payload.notes or "",
        )
    except Exception as e:
        logger.error(f"Failed to send candidate booking notifications: {e}")

    return booking


# ---------------------------------------------------------------------------
# Availability endpoint
# ---------------------------------------------------------------------------


@router.get("/availability/{date_str}")
def get_availability(date_str: str, db: Session = Depends(get_db)):
    from datetime import date

    try:
        query_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
        )

    taken = (
        db.query(Booking.time_slot)
        .filter(
            Booking.date == query_date,
            Booking.status.in_(["pending", "confirmed"]),
        )
        .all()
    )
    return {"date": date_str, "taken_slots": [row.time_slot for row in taken]}


# ---------------------------------------------------------------------------
# Employer endpoint — my bookings
# ---------------------------------------------------------------------------


@router.get("/my", response_model=List[BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return (
        db.query(Booking)
        .filter(Booking.employer_id == current_user.id)
        .order_by(Booking.date.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[BookingResponse])
def list_bookings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Booking).order_by(Booking.date.asc()).all()


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return booking


# ---------------------------------------------------------------------------
# Response page helper
# ---------------------------------------------------------------------------


def _response_page(
    title: str,
    message: str,
    success: bool,
    meeting_url: str = None,
    show_site_link: bool = False,
) -> str:
    icon = "✅" if success else "👋"
    accent = "#16a34a" if success else "#0a66c2"
    btn = ""
    if meeting_url:
        btn = f"""
        <a href="{meeting_url}"
           style="display:inline-block;margin-top:24px;background:#0a66c2;color:#fff;
                  text-decoration:none;font-weight:700;padding:14px 32px;border-radius:10px;
                  font-size:15px;font-family:sans-serif;">
            Join Zoom Call →
        </a>"""
    if show_site_link:
        btn = """
        <a href="https://ryzerecruiting.com"
           style="display:inline-block;margin-top:24px;background:#f0f2f5;color:#0a66c2;
                  text-decoration:none;font-weight:700;padding:14px 32px;border-radius:10px;
                  font-size:15px;font-family:sans-serif;">
            Visit RYZE Recruiting
        </a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title} — RYZE Recruiting</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap" rel="stylesheet"/>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'DM Sans',sans-serif;min-height:100vh;
             display:flex;align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:16px;padding:48px 40px;max-width:480px;width:100%;
              text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
    <div style="font-size:3rem;margin-bottom:16px;">{icon}</div>
    <div style="font-size:13px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
                color:{accent};margin-bottom:12px;">RYZE Recruiting</div>
    <h1 style="font-size:1.6rem;color:#1a1a2e;margin:0 0 16px;font-weight:700;">{title}</h1>
    <p style="font-size:1rem;color:#6b7280;line-height:1.6;margin:0;">{message}</p>
    {btn}
  </div>
</body>
</html>"""
