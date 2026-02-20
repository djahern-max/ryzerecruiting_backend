from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class BookingCreate(BaseModel):
    date: date
    time_slot: str          # e.g. "9:00 AM"
    phone: Optional[str] = None
    notes: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    status: str             # pending | confirmed | cancelled


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BookingResponse(BaseModel):
    id: int
    employer_id: int
    employer_name: str
    employer_email: str
    date: date
    time_slot: str
    phone: Optional[str]
    notes: Optional[str]
    status: str
    calendar_event_id: Optional[str]

    class Config:
        from_attributes = True
