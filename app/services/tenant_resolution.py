# app/services/tenant_resolution.py
"""
Decide which firm a self-registering Candidate / Employer belongs to.

There are no unplaced users (tenant restructure part 3). A person can
register only if exactly one firm already has a tenant-scoped profile for
their email — a `candidates` row for CANDIDATE, an `employer_profiles` row
(`primary_contact_email`) for EMPLOYER. Anything else is refused with an
HTTPException. Both callers (AuthService.create_user and
get_or_create_oauth_user) call this before constructing the User, so a
refusal never leaves a `users` row behind.

Firms get their tenant explicitly: /api/auth/signup-firm,
/api/admin/invite-firm, scripts/create_superadmin.py. ADMIN therefore never
legitimately reaches this function and is refused like a no-match.
"""
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.user import UserType

logger = logging.getLogger(__name__)

# Shown verbatim by the frontend.
NO_FIRM_DETAIL = (
    "No recruiting firm has you on file yet. Ask your recruiter to add you, "
    "then register with the same email."
)
MULTI_FIRM_DETAIL = "More than one firm has this email on file. Contact your recruiter."


def _no_firm() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NO_FIRM_DETAIL)


def resolve_signup_tenant(db: Session, email: str, user_type: UserType) -> str:
    """
    Return the slug of the one firm that has `email` on file for `user_type`.

    Raises 403 when no firm has the person (also for an empty email or a
    non-public user type) and 409 when more than one firm does — a single
    login can only point at one tenant, and guessing would leak a person
    into the wrong firm's book.
    """
    email = (email or "").strip()
    if not email:
        raise _no_firm()

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
        logger.warning(f"[signup] {email}: user_type {user_type!r} cannot self-register")
        raise _no_firm()

    firms = {t for (t,) in rows if t}

    if len(firms) == 1:
        return firms.pop()
    if len(firms) > 1:
        logger.warning(f"[signup] {email} matches multiple firms {sorted(firms)}; refused")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=MULTI_FIRM_DETAIL)
    raise _no_firm()
