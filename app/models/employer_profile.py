# app/models/employer_profile.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class EmployerProfile(Base):
    """
    Persistent intelligence record for each employer company.
    One record per company, enriched over time as more interactions occur.

    tenant_id is NULL for all RYZE Recruiting data.
    When RYZE.ai launches, other firms write with tenant_id = 'firm_abc123'.
    No migration required — RYZE Recruiting rows are already the first tenant.
    """

    __tablename__ = "employer_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # ── Identity ──────────────────────────────────────────────────────────
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    company_name = Column(String(255), nullable=False, index=True)
    website_url = Column(String(500), nullable=True)
    primary_contact_email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)

    # ── AI-generated structured intelligence ─────────────────────────────
    ai_industry = Column(String(255), nullable=True)
    ai_company_size = Column(String(100), nullable=True)
    ai_company_overview = Column(Text, nullable=True)
    ai_hiring_needs = Column(Text, nullable=True)  # JSON array stored as string
    ai_talking_points = Column(Text, nullable=True)  # JSON array stored as string
    ai_red_flags = Column(Text, nullable=True)
    ai_brief_raw = Column(Text, nullable=True)  # full brief text fallback
    ai_brief_updated_at = Column(DateTime(timezone=True), nullable=True)

    # ── Recruiter notes (manually added post-call) ────────────────────────
    recruiter_notes = Column(Text, nullable=True)
    relationship_status = Column(String(50), nullable=True)
    # prospect | active_client | placed | inactive | not_a_fit

    # ── RYZE.ai multi-tenancy scaffold (NULL = RYZE Recruiting) ───────────
    tenant_id = Column(String(100), nullable=True, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
