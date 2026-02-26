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
from app.services.email import (
    send_employer_confirmation,
    send_admin_notification,
    send_meeting_confirmed,
)
from app.services.zoom import create_meeting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


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
        # No meeting_url yet — created when admin confirms
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
        )
    except Exception as e:
        logger.error(f"Failed to send admin notification email: {e}")

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

    # When confirming — create Zoom meeting and email employer the link
    if payload.status == "confirmed" and booking.status != "confirmed":
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

        try:
            send_meeting_confirmed(
                employer_name=booking.employer_name,
                employer_email=booking.employer_email,
                company_name=booking.company_name or "",
                date=str(booking.date),
                time_slot=booking.time_slot,
                meeting_url=booking.meeting_url,
                phone=booking.phone or "",
                notes=booking.notes or "",
            )

        except Exception as e:
            logger.error(f"Failed to send meeting confirmed email: {e}")

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
