# app/models/candidate.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=1, nullable=False)

    # Contact info
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # LinkedIn
    linkedin_url = Column(String, nullable=True)
    linkedin_raw_text = Column(Text, nullable=True)

    # Current position
    current_title = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    location = Column(String, nullable=True)

    # AI generated fields
    ai_summary = Column(Text, nullable=True)
    ai_outreach_message = Column(Text, nullable=True)
    ai_parsed_at = Column(DateTime, nullable=True)

    # Recruiter notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
