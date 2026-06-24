# app/services/branding.py
"""
Tenant-aware branding + sender resolution.

Every outbound message — email via Resend, SMS via Twilio — carries a sender
identity and a brand voice. On a multi-tenant platform that identity should
belong to the *firm the message is about*, not to RYZE globally.

get_branding(db, tenant_id) returns a TenantBranding whose every field falls
back, individually, to RYZE's global defaults (app.core.config.settings).
A brand-new tenant with all-null override columns therefore behaves EXACTLY
like RYZE does today — this layer is regression-safe by construction, and is
safe to call with db=None or an unknown tenant (you get RYZE defaults).

SECRET HANDLING: tenant.twilio_auth_token is a credential. The column exists
as a stub for the future per-number model. Do NOT populate it in production
until it is encrypted at rest (Fernet / cloud KMS). In the shared-sender model
every tenant leaves the twilio_* columns NULL and rides on RYZE's number.

RESEND NOTE: from_email must be a domain verified in Resend. Until a firm
verifies its own domain, leave from_email NULL — messages then send from RYZE's
verified address with the firm's name as the display name and the firm's
address as reply_to. That gives a white-label feel with no domain setup.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant import Tenant

RYZE_TENANT = "ryze"


@dataclass(frozen=True)
class TenantBranding:
    tenant_id: str
    brand_name: str  # display name: "RYZE.ai" or "Acme Recruiting"
    signature_name: str  # who signs emails: "Dane"
    from_email: str  # Resend-verified sender address
    reply_to_email: str  # where replies land
    admin_email: str  # internal/admin notifications for this firm
    support_email: str  # HELP / support contact
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str

    @property
    def email_from_line(self) -> str:
        # Resend "from" header, e.g. 'Acme Recruiting <dane@ryze.ai>'
        return f"{self.brand_name} <{self.from_email}>"

    @property
    def has_sms(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
        )


def _ryze_defaults(tenant_id: str) -> TenantBranding:
    return TenantBranding(
        tenant_id=tenant_id,
        brand_name="RYZE.ai",
        signature_name="Dane",
        from_email=settings.FROM_EMAIL,
        reply_to_email=settings.FROM_EMAIL,
        admin_email=settings.ADMIN_EMAIL,
        support_email=settings.FROM_EMAIL,
        twilio_account_sid=settings.TWILIO_ACCOUNT_SID,
        twilio_auth_token=settings.TWILIO_AUTH_TOKEN,
        twilio_from_number=settings.TWILIO_FROM_NUMBER,
    )


def get_branding(db: Optional[Session], tenant_id: Optional[str]) -> TenantBranding:
    """Resolve branding for a tenant; every field falls back to RYZE globals.

    getattr(..., None) is used for the override columns so this still works
    BEFORE the migration adds them — deploy the code first, migrate second,
    with no window of breakage.
    """
    tid = tenant_id or RYZE_TENANT
    defaults = _ryze_defaults(tid)

    if db is None or tid == RYZE_TENANT:
        return defaults

    tenant = db.query(Tenant).filter(Tenant.slug == tid).first()
    if tenant is None:
        return defaults

    def pick(override, fallback):
        if isinstance(override, str):
            override = override.strip()
        return override or fallback

    return TenantBranding(
        tenant_id=tid,
        brand_name=pick(tenant.company_name, defaults.brand_name),
        signature_name=pick(
            getattr(tenant, "signature_name", None), defaults.signature_name
        ),
        from_email=pick(getattr(tenant, "from_email", None), defaults.from_email),
        reply_to_email=pick(
            getattr(tenant, "reply_to_email", None), defaults.reply_to_email
        ),
        admin_email=pick(getattr(tenant, "admin_email", None), defaults.admin_email),
        support_email=pick(
            getattr(tenant, "support_email", None), defaults.support_email
        ),
        twilio_account_sid=pick(
            getattr(tenant, "twilio_account_sid", None), defaults.twilio_account_sid
        ),
        twilio_auth_token=pick(
            getattr(tenant, "twilio_auth_token", None), defaults.twilio_auth_token
        ),
        twilio_from_number=pick(
            getattr(tenant, "twilio_from_number", None), defaults.twilio_from_number
        ),
    )
