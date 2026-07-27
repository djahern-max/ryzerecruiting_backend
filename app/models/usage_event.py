# app/models/usage_event.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Index
from app.core.database import Base


class UsageEvent(Base):
    """
    One row per metered AI API call (Anthropic or OpenAI).

    created_at is naive UTC (datetime.utcnow), matching the naive
    datetime.utcnow() used by app.services.usage's month-boundary math —
    do not switch this to a timezone-aware column without updating that
    comparison too.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)

    provider = Column(String(20), nullable=False)  # "anthropic" | "openai"
    model = Column(String(100), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)

    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
