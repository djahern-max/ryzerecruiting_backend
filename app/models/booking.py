# app/models/booking.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # ── Employer who made the booking ─────────────────────────────────────
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    employer_name = Column(String(255), nullable=False)
    employer_email = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    website_url = Column(String(500), nullable=True)

    # ── Booking details ───────────────────────────────────────────────────
    date = Column(Date, nullable=False)
    time_slot = Column(String(20), nullable=False)  # e.g. "9:00 AM"
    phone = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)

    # ── Status tracking ───────────────────────────────────────────────────
    status = Column(String(20), nullable=False, default="pending")
    # pending | confirmed | cancelled

    # ── Meeting & Calendar ────────────────────────────────────────────────
    meeting_url = Column(String(500), nullable=True)
    calendar_event_id = Column(String(255), nullable=True)

    # ── Intelligence layer (Data Strategy) ───────────────────────────────
    # Link to the persistent employer intelligence profile
    employer_profile_id = Column(
        Integer, ForeignKey("employer_profiles.id"), nullable=True
    )

    # Post-call outcome — filled in by recruiter after the meeting
    call_outcome = Column(String(50), nullable=True)
    # completed | no_show | rescheduled | not_a_fit | promising | placement_started

    call_notes = Column(Text, nullable=True)  # recruiter notes from this specific call

    # ── Scheduler / automation ────────────────────────────────────────────
    reminded_at = Column(
        DateTime(timezone=True), nullable=True
    )  # Task 4: reminder dedup

    # ── Zoom AI notes ─────────────────────────────────────────────────────
    meeting_summary = Column(Text, nullable=True)  # Task 5: Zoom AI Companion output

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
