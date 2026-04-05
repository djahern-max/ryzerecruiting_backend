# app/models/candidate.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from pgvector.sqlalchemy import Vector
from app.core.database import Base

RYZE_TENANT = "ryze"


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    # Multi-tenancy — 'ryze' = RYZE Recruiting (default tenant)
    tenant_id = Column(String(100), nullable=True, default=RYZE_TENANT, index=True)

    # Contact info
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # Source — how this record was created
    # "manual"  = recruiter added via UI (resume upload, LinkedIn paste, manual entry)
    # "booking" = auto-created when an outbound_candidate booking was confirmed
    source = Column(String(50), nullable=True, default="manual")

    # Source fields
    linkedin_url = Column(String, nullable=True)
    linkedin_raw_text = Column(Text, nullable=True)

    # Current position
    current_title = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    location = Column(String, nullable=True)

    # AI generated fields — core
    ai_summary = Column(Text, nullable=True)
    ai_career_level = Column(String, nullable=True)  # junior | mid | senior | executive
    ai_outreach_message = Column(Text, nullable=True)
    ai_parsed_at = Column(DateTime, nullable=True)

    # AI generated fields — structured profile
    ai_experience = Column(Text, nullable=True)
    ai_education = Column(Text, nullable=True)
    ai_certifications = Column(Text, nullable=True)
    ai_skills = Column(JSON, nullable=True)
    ai_years_experience = Column(Integer, nullable=True)

    # Call transcript — copied from booking.meeting_transcript when Zoom webhook fires
    # Stored here so RYZE Intelligence can find this candidate by what was said on the call
    meeting_transcript = Column(Text, nullable=True)

    # Recruiter notes
    notes = Column(Text, nullable=True)

    # RAG / PGVector
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
