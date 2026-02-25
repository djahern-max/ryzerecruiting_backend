# app/schemas/booking.py
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import date


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class BookingCreate(BaseModel):
    date: date
    time_slot: str
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    status: str  # pending | confirmed | cancelled


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class BookingResponse(BaseModel):
    id: int
    employer_id: int
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

    class Config:
        from_attributes = True
