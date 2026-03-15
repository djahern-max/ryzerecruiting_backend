# app/models/candidate.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=1, nullable=False)

    # Contact info
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # Source
    linkedin_url = Column(String, nullable=True)
    linkedin_raw_text = Column(Text, nullable=True)  # stores paste content (any source)

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

    # Recruiter notes
    notes = Column(Text, nullable=True)

    # RAG / PGVector — 1536 dims matches OpenAI text-embedding-3-small
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
