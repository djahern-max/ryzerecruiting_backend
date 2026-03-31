# app/models/employer_profile.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class EmployerProfile(Base):
    __tablename__ = "employer_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    company_name = Column(String(255), nullable=False, index=True)
    website_url = Column(String(500), nullable=True)
    primary_contact_email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)

    # AI-generated structured intelligence
    ai_industry = Column(String(255), nullable=True)
    ai_company_size = Column(Text, nullable=True)
    ai_company_overview = Column(Text, nullable=True)
    ai_hiring_needs = Column(Text, nullable=True)  # JSON array stored as string
    ai_talking_points = Column(Text, nullable=True)  # JSON array stored as string
    ai_red_flags = Column(Text, nullable=True)
    ai_brief_raw = Column(Text, nullable=True)
    ai_brief_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Recruiter notes
    recruiter_notes = Column(Text, nullable=True)
    relationship_status = Column(String(50), nullable=True)

    # Raw source text (original paste / job posting used to create this profile)
    raw_text = Column(Text, nullable=True)

    # Multi-tenancy scaffold (NULL = RYZE.ai)
    tenant_id = Column(String(100), nullable=True, default="ryze", index=True)

    # RAG / PGVector
    embedding = Column(Vector(1536), nullable=True)
    embedded_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
