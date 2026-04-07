# app/models/candidate.py
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)

    # ── Multi-tenancy ─────────────────────────────────────────────────────
    tenant_id = Column(String(100), nullable=True, index=True)

    # ── Identity ──────────────────────────────────────────────────────────
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    linkedin_raw_text = Column(Text, nullable=True)

    # ── Current position ──────────────────────────────────────────────────
    current_title = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    location = Column(String, nullable=True)

    # ── AI-parsed fields ──────────────────────────────────────────────────
    ai_summary = Column(Text, nullable=True)
    ai_career_level = Column(String, nullable=True)
    ai_outreach_message = Column(Text, nullable=True)
    ai_parsed_at = Column(DateTime, nullable=True)
    ai_experience = Column(Text, nullable=True)
    ai_education = Column(Text, nullable=True)
    ai_certifications = Column(Text, nullable=True)
    ai_skills = Column(JSON, nullable=True)
    ai_years_experience = Column(Integer, nullable=True)

    # ── Recruiter notes ───────────────────────────────────────────────────
    notes = Column(Text, nullable=True)

    # ── Source & origin tracking (EP18) ──────────────────────────────────
    # How this candidate record was created.
    # Values: 'booking' | 'resume' | 'linkedin' | 'manual'
    source = Column(String(50), nullable=True)

    # Back-reference to the booking that auto-created this candidate (EP18).
    # Nullable — only set when source='booking'. SET NULL on booking delete
    # so removing a booking doesn't orphan the candidate.
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Call data (EP18) ─────────────────────────────────────────────────
    # Transcript copied from the linked booking's Zoom call so RYZE
    # Intelligence can search by what was said, not just resume content.
    meeting_transcript = Column(Text, nullable=True)

    # ── Embedding ─────────────────────────────────────────────────────────
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
