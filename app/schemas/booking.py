# app/schemas/booking.py
from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from datetime import date, datetime


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class BookingCreate(BaseModel):
    """Employer self-books via the booking form — original inbound flow."""

    date: date
    time_slot: str
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class RecruiterInviteCreate(BaseModel):
    """Recruiter sends an outbound meeting invite to an employer or candidate contact."""

    invite_type: Literal["outbound_employer", "outbound_candidate"]
    contact_name: str
    contact_email: EmailStr
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    date: date
    time_slot: str
    notes: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    status: str  # pending | confirmed | cancelled


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class BookingResponse(BaseModel):
    id: int
    booking_type: str
    employer_id: Optional[int]
    employer_name: str
    employer_email: str
    company_name: Optional[str]
    website_url: Optional[str]
    date: date
    time_slot: str
    phone: Optional[str]
    notes: Optional[str]
    status: str
    meeting_url: Optional[str]
    calendar_event_id: Optional[str]

    # Intelligence layer — employer
    employer_profile_id: Optional[int] = None

    # Intelligence layer — candidate (EP17)
    # Set when a candidate booking is confirmed — links to the auto-created Candidate record
    candidate_id: Optional[int] = None

    # Call outcome & notes
    call_outcome: Optional[str] = None
    call_notes: Optional[str] = None

    # Meeting intelligence
    reminded_at: Optional[datetime] = None
    meeting_summary: Optional[str] = None
    meeting_next_steps: Optional[str] = None
    meeting_keywords: Optional[str] = None

    class Config:
        from_attributes = True


class CandidateBookingCreate(BaseModel):
    """Candidate self-books via the candidate booking form."""

    name: str
    date: date
    time_slot: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
