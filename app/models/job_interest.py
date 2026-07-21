# app/models/job_interest.py
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from app.core.database import Base

RYZE_TENANT = "ryze"


class JobInterest(Base):
    __tablename__ = "job_interests"
    __table_args__ = (
        UniqueConstraint(
            "job_order_id", "candidate_id", name="uq_job_interest_job_candidate"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # ── Multi-tenancy ─────────────────────────────────────────────────────
    tenant_id = Column(String(100), nullable=True, default=RYZE_TENANT, index=True)

    job_order_id = Column(Integer, ForeignKey("job_orders.id"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)

    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
