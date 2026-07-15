# app/services/tenant_resolution.py
import logging

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.user import UserType
from app.core.deps import RYZE_TENANT

logger = logging.getLogger(__name__)


def resolve_signup_tenant(db: Session, email: str, user_type: UserType) -> str:
    """
    Decide which tenant a self-registering candidate/employer belongs to.

    A person belongs to whichever firm already has a tenant-scoped profile for
    their email. No prior firm association → RYZE's own book (RYZE_TENANT).
    ADMIN never reaches here — firms are created with an explicit tenant via
    the invite flow.
    """
    email = (email or "").strip()
    if not email:
        return RYZE_TENANT

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
        return RYZE_TENANT

    firms = {t for (t,) in rows if t and t != RYZE_TENANT}

    if len(firms) == 1:
        return firms.pop()
    if len(firms) > 1:
        # One email tied to multiple firms — a single login can only point at
        # one tenant. Don't silently pick a winner; leave in ryze and flag.
        logger.warning(
            f"[signup] {email} matches multiple firms {sorted(firms)}; "
            f"leaving in {RYZE_TENANT} for manual assignment"
        )
        return RYZE_TENANT
    return RYZE_TENANT
