# app/services/tenant_resolution.py
import logging

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.user import UserType
# Part 3 decides what happens to unplaced signups. Until then they land in a
# slug with no tenants row, which get_current_tenant rejects with 403.
_LEGACY_UNPLACED = "ryze"

logger = logging.getLogger(__name__)


def resolve_signup_tenant(db: Session, email: str, user_type: UserType) -> str:
    """
    Decide which tenant a self-registering candidate/employer belongs to.

    A person belongs to whichever firm already has a tenant-scoped profile for
    their email. No prior firm association → RYZE's own book (_LEGACY_UNPLACED).
    ADMIN never reaches here — firms are created with an explicit tenant via
    the invite flow.
    """
    email = (email or "").strip()
    if not email:
        return _LEGACY_UNPLACED

    if user_type == UserType.CANDIDATE:
        rows = (
            db.query(Candidate.tenant_id)
            .filter(Candidate.email.ilike(email))
            .distinct()
            .all()
        )
    elif user_type == UserType.EMPLOYER:
        rows = (
            db.query(EmployerProfile.tenant_id)
            .filter(EmployerProfile.primary_contact_email.ilike(email))
            .distinct()
            .all()
        )
    else:
        return _LEGACY_UNPLACED

    firms = {t for (t,) in rows if t and t != _LEGACY_UNPLACED}

    if len(firms) == 1:
        return firms.pop()
    if len(firms) > 1:
        # One email tied to multiple firms — a single login can only point at
        # one tenant. Don't silently pick a winner; leave in ryze and flag.
        logger.warning(
            f"[signup] {email} matches multiple firms {sorted(firms)}; "
            f"leaving in {_LEGACY_UNPLACED} for manual assignment"
        )
        return _LEGACY_UNPLACED
    return _LEGACY_UNPLACED
