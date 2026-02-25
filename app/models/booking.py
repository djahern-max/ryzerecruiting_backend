# app/models/booking.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # Employer who made the booking
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    employer_name = Column(String(255), nullable=False)
    employer_email = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    website_url = Column(String(500), nullable=True)

    # Booking details
    date = Column(Date, nullable=False)
    time_slot = Column(String(20), nullable=False)  # e.g. "9:00 AM"
    phone = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)

    # Status tracking
    status = Column(String(20), nullable=False, default="pending")
    # pending | confirmed | cancelled

    # Meeting & Calendar
    meeting_url = Column(
        String(500), nullable=True
    )  # static Zoom link for now → dynamic later
    calendar_event_id = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
