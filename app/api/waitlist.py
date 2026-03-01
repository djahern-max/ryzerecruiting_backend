# app/api/waitlist.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.waitlist import Waitlist
from app.api.auth import get_current_user
from app.schemas.waitlist import WaitlistCreate, WaitlistResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])


# ---------------------------------------------------------------------------
# Public endpoint — submit email
# ---------------------------------------------------------------------------


@router.post("", response_model=WaitlistResponse, status_code=status.HTTP_201_CREATED)
def join_waitlist(payload: WaitlistCreate, db: Session = Depends(get_db)):
    """
    Add an email to the waitlist.
    Returns 409 if the email already exists (frontend treats this as success).
    """
    entry = Waitlist(email=payload.email.lower(), source=payload.source)
    db.add(entry)
    try:
        db.commit()
        db.refresh(entry)
        logger.info(f"Waitlist signup: {entry.email}")
        return entry
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already on the waitlist.",
        )


# ---------------------------------------------------------------------------
# Admin endpoint — view signups
# ---------------------------------------------------------------------------


@router.get("", response_model=list[WaitlistResponse])
def list_waitlist(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Admin-only: returns all waitlist entries, newest first."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return db.query(Waitlist).order_by(Waitlist.created_at.desc()).all()
