# app/api/bookings.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.database import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingStatusUpdate, BookingResponse
from app.api.auth import get_current_user
from app.models.user import User
from app.core.config import settings
from app.services.email import send_employer_confirmation, send_admin_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


# ---------------------------------------------------------------------------
# Meeting URL helper — swap this function when upgrading to Zoom API
# ---------------------------------------------------------------------------


def get_meeting_url() -> str:
    """Return the meeting URL for a booking. Static for now; replace with Zoom API call later."""
    return settings.ZOOM_MEETING_URL  # add ZOOM_MEETING_URL to your .env


# ---------------------------------------------------------------------------
# Admin guard
# ---------------------------------------------------------------------------


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.email != settings.ADMIN_EMAIL:
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
    meeting_url = get_meeting_url()

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
        meeting_url=meeting_url,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    try:
        send_employer_confirmation(
            employer_name=current_user.full_name,
            employer_email=current_user.email,
            company_name=payload.company_name or "",
            date=str(payload.date),
            time_slot=payload.time_slot,
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"Failed to send employer confirmation email: {e}")

    try:
        send_admin_notification(
            employer_name=current_user.full_name,
            employer_email=current_user.email,
            company_name=payload.company_name or "",
            website_url=payload.website_url or "",
            date=str(payload.date),
            time_slot=payload.time_slot,
            phone=payload.phone or "",
            notes=payload.notes or "",
            meeting_url=meeting_url,
        )
    except Exception as e:
        logger.error(f"Failed to send admin notification email: {e}")

    # TODO (Phase 4): create Google Calendar event

    return booking


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
