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

    # ── Multi-tenancy ─────────────────────────────────────────────────────
    tenant_id = Column(String(100), nullable=True, index=True)

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

    # ── Intelligence layer — employer ──────────────────────────────────────
    employer_profile_id = Column(
        Integer, ForeignKey("employer_profiles.id"), nullable=True
    )

    # ── Intelligence layer — candidate ────────────────────────────────────
    # Set when an outbound_candidate or inbound_candidate booking is confirmed.
    # Points to the auto-created (or matched) Candidate record so transcripts,
    # summaries, and call data are linked to the right person.
    candidate_id = Column(
        Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Call outcome & notes (recruiter-filled post-call) ─────────────────
    call_outcome = Column(String(50), nullable=True)
    call_notes = Column(Text, nullable=True)

    # ── AI meeting intelligence (Zoom webhook populated) ──────────────────
    meeting_summary = Column(Text, nullable=True)
    meeting_next_steps = Column(Text, nullable=True)
    meeting_keywords = Column(Text, nullable=True)
    meeting_transcript = Column(Text, nullable=True)

    # ── Reminder tracking ─────────────────────────────────────────────────
    reminded_at = Column(DateTime, nullable=True)

    # ── Embedding ─────────────────────────────────────────────────────────
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
