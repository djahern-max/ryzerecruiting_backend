# app/api/waitlist.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.waitlist import Waitlist
from app.api.auth import require_admin  # reuse existing admin guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WaitlistCreate(BaseModel):
    email: EmailStr
    source: str = "landing_page"


class WaitlistResponse(BaseModel):
    id: int
    email: str
    source: str | None

    class Config:
        from_attributes = True


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
def list_waitlist(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Admin-only: returns all waitlist entries, newest first."""
    return db.query(Waitlist).order_by(Waitlist.created_at.desc()).all()
