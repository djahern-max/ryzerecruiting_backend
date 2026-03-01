# app/api/bookings.py
from datetime import datetime
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.config import settings
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.booking import Booking
from app.models.employer_profile import EmployerProfile
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingStatusUpdate, BookingResponse
from app.services.ai_brief import generate_pre_call_brief
from app.services.calendar import create_calendar_event, delete_calendar_event
from app.services.notifications import (
    notify_booking_received,
    notify_booking_confirmed,
    notify_booking_cancelled,
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
# Employer endpoint — create a booking
# ---------------------------------------------------------------------------


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = Booking(
        employer_id=current_user.id,
        employer_name=current_user.full_name,
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
            employer_name=current_user.full_name,
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


@router.get("/my", response_model=List[BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employer sees only their own bookings, ordered soonest first."""
    return (
        db.query(Booking)
        .filter(Booking.employer_id == current_user.id)
        .order_by(Booking.date.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Availability endpoint — Phase 3B: block taken time slots
# ---------------------------------------------------------------------------


@router.get("/availability/{date_str}")
def get_availability(
    date_str: str,
    db: Session = Depends(get_db),
):
    """
    Returns a list of time slots already taken on a given date.
    Frontend uses this to disable busy slots in the booking form.
    Format: YYYY-MM-DD
    """
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
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[BookingResponse])
def list_bookings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(Booking).order_by(Booking.date.asc()).all()


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return booking


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
    if payload.status not in ("pending", "confirmed", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status value.")

    # ── Confirming: create Zoom meeting, build employer intelligence, notify ──
    if payload.status == "confirmed" and booking.status != "confirmed":

        # 1. Create Zoom meeting
        try:
            zoom = create_meeting(
                topic=f"RYZE Recruiting — {booking.company_name or booking.employer_name}",
                date=str(booking.date),
                time_slot=booking.time_slot,
            )
            booking.meeting_url = zoom["join_url"]
            logger.info(f"Zoom meeting created: {zoom['meeting_id']}")
        except Exception as e:
            logger.error(f"Failed to create Zoom meeting: {e}")
            raise HTTPException(
                status_code=500, detail=f"Could not create Zoom meeting: {str(e)}"
            )

        # 2. Create Google Calendar event
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
            logger.error(f"Failed to create Google Calendar event: {e}")
            # Non-fatal: don't block the confirmation

        # 3. Generate structured AI brief from employer website
        brief_dict = {}
        if booking.website_url:
            try:
                brief_dict = generate_pre_call_brief(booking.website_url)
                logger.info(f"AI brief generated for {booking.website_url}")
            except Exception as e:
                logger.error(f"Failed to generate AI brief: {e}")

        # 4. Upsert employer_profiles record with AI intelligence
        try:
            profile = (
                db.query(EmployerProfile)
                .filter(
                    EmployerProfile.company_name == booking.company_name,
                    EmployerProfile.tenant_id.is_(None),
                )
                .first()
            )

            if not profile:
                profile = EmployerProfile(
                    company_name=booking.company_name or "",
                    website_url=booking.website_url,
                    primary_contact_email=booking.employer_email,
                    phone=booking.phone,
                    user_id=booking.employer_id,
                    tenant_id=None,
                )
                db.add(profile)
                logger.info(f"Created new employer profile for: {booking.company_name}")
            else:
                if booking.website_url:
                    profile.website_url = booking.website_url
                if booking.phone:
                    profile.phone = booking.phone
                logger.info(
                    f"Updating existing employer profile for: {booking.company_name}"
                )

            if brief_dict:
                profile.ai_industry = brief_dict.get("industry")
                profile.ai_company_size = brief_dict.get("estimated_size")
                profile.ai_company_overview = brief_dict.get("company_overview")
                profile.ai_hiring_needs = json.dumps(brief_dict.get("hiring_needs", []))
                profile.ai_talking_points = json.dumps(
                    brief_dict.get("talking_points", [])
                )
                profile.ai_red_flags = brief_dict.get("red_flags")
                profile.ai_brief_raw = brief_dict.get("ai_brief_raw", "")
                profile.ai_brief_updated_at = datetime.utcnow()

            db.flush()
            booking.employer_profile_id = profile.id

        except Exception as e:
            logger.error(f"Failed to upsert employer profile: {e}")

        # 5. Send confirmation notifications (email + SMS)
        try:
            notify_booking_confirmed(
                employer_name=booking.employer_name,
                email=booking.employer_email,
                phone=booking.phone or "",
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
                notes=booking.notes or "",
                ai_brief=brief_dict,
            )
        except Exception as e:
            logger.error(f"Failed to send booking confirmed notifications: {e}")

    # ── Cancelling: delete calendar event, notify employer ──
    if payload.status == "cancelled" and booking.status != "cancelled":

        # Delete Google Calendar event if one exists
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
