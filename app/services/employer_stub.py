# app/services/employer_stub.py
"""
Employer stub creation service.

When an outbound_employer, inbound, or inbound-self-booked employer booking
is confirmed, an EmployerProfile should be born at that moment — even if the
contact never shares a company website — so meeting notes and future AI
enrichment have somewhere to attach, and so the profile can later be linked
to a signed-up user by email (see employer_profiles.py _resolve_employer_for_user).
Mirrors candidate_stub.py's find-or-create pattern.

Dedup: matches an existing profile within the same tenant by contact email
first (the same key used to link a profile to a signed-up user), then by
website_url, else creates a fresh stub.
"""
import logging
from sqlalchemy.orm import Session

from app.models.employer_profile import EmployerProfile

logger = logging.getLogger(__name__)


def find_or_create_employer_stub(
    db: Session,
    booking,  # Booking ORM instance
    tenant_id: str,
) -> EmployerProfile:
    """
    Find an existing employer profile by contact email or website_url (within
    the same tenant) or create a minimal stub. Sets booking.employer_profile_id.

    Does NOT commit — the caller is responsible for committing. Uses
    db.flush() to generate profile.id when a new record is created so the
    caller can set booking.employer_profile_id before the final commit.

    Returns the EmployerProfile instance (new or existing).
    """
    profile = None

    # ── Try email match first — this is the same key signup-linking uses ──
    if booking.employer_email:
        profile = (
            db.query(EmployerProfile)
            .filter(
                EmployerProfile.primary_contact_email.ilike(booking.employer_email),
                EmployerProfile.tenant_id == tenant_id,
            )
            .first()
        )
        if profile:
            logger.info(
                f"[employer_stub] Linked existing profile #{profile.id} "
                f"({profile.company_name}) to booking #{booking.id} — matched by email"
            )

    # ── Fall back to website_url match ─────────────────────────────────────
    if not profile and booking.website_url:
        profile = (
            db.query(EmployerProfile)
            .filter(
                EmployerProfile.website_url == booking.website_url,
                EmployerProfile.tenant_id == tenant_id,
            )
            .first()
        )
        if profile:
            logger.info(
                f"[employer_stub] Linked existing profile #{profile.id} "
                f"({profile.company_name}) to booking #{booking.id} — matched by website"
            )
            if not profile.primary_contact_email and booking.employer_email:
                profile.primary_contact_email = booking.employer_email

    # ── Create stub if no match found ──────────────────────────────────────
    if not profile:
        profile = EmployerProfile(
            tenant_id=tenant_id,
            company_name=booking.company_name or booking.employer_name or "",
            website_url=booking.website_url,
            primary_contact_email=booking.employer_email or None,
            phone=booking.phone or None,
        )
        db.add(profile)
        db.flush()  # generate profile.id without committing the transaction

        logger.info(
            f"[employer_stub] Created stub profile #{profile.id} "
            f"({profile.company_name}) for booking #{booking.id}"
        )

    # ── Link booking → profile (forward reference) ─────────────────────────
    booking.employer_profile_id = profile.id
    # Caller commits

    return profile
