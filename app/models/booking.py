# app/models/booking.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
from pgvector.sqlalchemy import Vector


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # ── Booking type ──────────────────────────────────────────────────────
    # inbound            = employer self-booked via booking form
    # outbound_employer  = recruiter sent invite to an employer contact
    # outbound_candidate = recruiter sent invite to a candidate
    # inbound_candidate  = candidate self-booked via candidate form
    booking_type = Column(String(30), nullable=False, default="inbound")

    # ── Employer / contact ────────────────────────────────────────────────
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    employer_name = Column(String(255), nullable=False)
    employer_email = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    website_url = Column(String(500), nullable=True)

    # ── Booking details ───────────────────────────────────────────────────
    date = Column(Date, nullable=False)
    time_slot = Column(String(20), nullable=False)
    phone = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)

    # ── Status tracking ───────────────────────────────────────────────────
    status = Column(String(20), nullable=False, default="pending")
    # pending | confirmed | cancelled

    # ── Accept/Decline token (outbound invites) ───────────────────────────
    # Generated on recruiter-invite creation, cleared after use
    response_token = Column(String(100), nullable=True)

    # ── Meeting & Calendar ────────────────────────────────────────────────
    meeting_url = Column(String(500), nullable=True)
    calendar_event_id = Column(String(255), nullable=True)

    # ── Intelligence layer ────────────────────────────────────────────────
    employer_profile_id = Column(
        Integer, ForeignKey("employer_profiles.id"), nullable=True
    )
    call_outcome = Column(String(50), nullable=True)
    call_notes = Column(Text, nullable=True)

    # ── Scheduler / automation ────────────────────────────────────────────
    reminded_at = Column(DateTime(timezone=True), nullable=True)

    # ── Zoom AI notes ─────────────────────────────────────────────────────
    meeting_summary = Column(Text, nullable=True)  # overview paragraph (existing)
    meeting_next_steps = Column(Text, nullable=True)  # action items Zoom extracted
    meeting_keywords = Column(Text, nullable=True)  # comma-separated key topics
    meeting_transcript = Column(Text, nullable=True)  # full word-for-word dialogue

    tenant_id = Column(String(100), nullable=True, default="ryze", index=True)

    # ── Embedding (for meeting notes semantic search) ─────────────────────
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
