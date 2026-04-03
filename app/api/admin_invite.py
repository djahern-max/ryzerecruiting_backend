# app/api/admin_invite.py
# EP17: Admin-only endpoint to onboard a new recruiting firm.
# Creates a tenant row, a user account, and fires a welcome email in one action.

import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin_user
from app.core.security import get_password_hash
from app.models.tenant import Tenant
from app.models.user import User, UserType
from app.services.email import send_welcome_invite_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    company_name: str
    full_name: str
    email: EmailStr


class InviteResponse(BaseModel):
    tenant_slug: str
    user_id: int
    trial_ends_at: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_slug(company_name: str, db: Session) -> str:
    """
    Convert company_name to a URL-safe slug.
    Appends a short random suffix if the slug is already taken.
    e.g. 'Acme Recruiting' → 'acme_recruiting'
    """
    base = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
    slug = base

    # Check for collision and append suffix if needed
    attempt = 0
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        attempt += 1
        slug = f"{base}_{attempt}"

    return slug


def _generate_temp_password(length: int = 12) -> str:
    """Generate a readable temporary password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED
)
def invite_firm(
    payload: InviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Onboard a new recruiting firm in one action:
      1. Validate no existing user with that email
      2. Generate a tenant slug from company_name
      3. Create Tenant row (status=trial, 30-day window)
      4. Create User row linked to the new tenant
      5. Fire branded welcome email via Resend
    """

    # Restrict to RYZE superadmin only
    if current_user.tenant_id != "ryze":
        raise HTTPException(status_code=403, detail="Not authorized.")

    # 1. Check for duplicate email
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A user with email {payload.email} already exists.",
        )

    # 2. Generate slug
    slug = _generate_slug(payload.company_name, db)

    # 3. Create Tenant
    now = datetime.now(timezone.utc)
    trial_ends = now + timedelta(days=30)

    tenant = Tenant(
        slug=slug,
        company_name=payload.company_name,
        status="trial",
        trial_starts_at=now,
        trial_ends_at=trial_ends,
    )
    db.add(tenant)
    db.flush()  # get tenant.id without committing

    # 4. Create User
    temp_password = _generate_temp_password()

    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(temp_password),
        user_type=UserType.ADMIN,
        is_superuser=True,
        is_active=True,
        tenant_id=slug,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(
        f"[invite] New tenant created — slug={slug} user={payload.email} "
        f"trial_ends={trial_ends.strftime('%Y-%m-%d')}"
    )

    # 5. Fire welcome email
    try:
        send_welcome_invite_email(
            full_name=payload.full_name,
            email=payload.email,
            temp_password=temp_password,
            company_name=payload.company_name,
            trial_ends_at=trial_ends,
        )
    except Exception as e:
        logger.error(f"[invite] Welcome email failed for {payload.email}: {e}")
        # Don't roll back — tenant and user are created. Email failure is non-fatal.

    return InviteResponse(
        tenant_slug=slug,
        user_id=new_user.id,
        trial_ends_at=trial_ends.strftime("%B %d, %Y"),
        message=f"Invite sent to {payload.email}. Trial ends {trial_ends.strftime('%B %d, %Y')}.",
    )
