# app/models/tenant.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)

    # URL-safe identifier — matches tenant_id on all other tables
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Display name used in emails and UI
    company_name = Column(String(255), nullable=False)

    # trial | active | expired | cancelled
    status = Column(String(20), nullable=False, default="trial")

    # Trial window
    trial_starts_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Stripe — populated after successful checkout
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    # ── White-label sender overrides (nullable → fall back to RYZE globals) ──
    # Resolved by app/services/branding.py. Leave NULL to use RYZE's shared
    # sender — a tenant with all-null overrides behaves exactly like RYZE today.
    from_email = Column(String(255), nullable=True)
    reply_to_email = Column(String(255), nullable=True)
    support_email = Column(String(255), nullable=True)
    signature_name = Column(String(100), nullable=True)

    # Per-tenant Twilio (future per-number / ISV model). Stubs for now — leave
    # NULL to ride on RYZE's shared number + A2P campaign.
    # SECURITY: encrypt twilio_auth_token at rest before populating in prod.
    twilio_account_sid = Column(String(100), nullable=True)
    twilio_auth_token = Column(String(255), nullable=True)
    twilio_from_number = Column(String(30), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
