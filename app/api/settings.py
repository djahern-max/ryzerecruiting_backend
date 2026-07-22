# app/api/settings.py
# User account settings — change password, future settings here.

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin_tenant
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Confirm new passwords match
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    # Enforce minimum length
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters.",
        )

    # Verify current password is correct
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    # Save new password
    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    logger.info(f"[settings] Password changed for user={current_user.email}")

    return {"message": "Password updated successfully."}


class TenantBrandingResponse(BaseModel):
    slug: str
    company_name: str
    reply_to_email: Optional[str] = None
    support_email: Optional[str] = None
    admin_email: Optional[str] = None
    signature_name: Optional[str] = None

    class Config:
        from_attributes = True


class TenantBrandingUpdate(BaseModel):
    """
    Fields a firm admin may edit on their own tenant.

    Intentionally EXCLUDED (platform-owned — only RYZE controls these):
      slug, status, trial dates, stripe_*, and the twilio_* credential stubs.
    company_name is also excluded here; renaming the firm is a heavier action
    (it changes the brand_name everywhere) and is better handled deliberately,
    not via a casual settings PATCH.
    """

    from_email: Optional[str] = None
    reply_to_email: Optional[str] = None
    support_email: Optional[str] = None
    admin_email: Optional[str] = None
    signature_name: Optional[str] = None

    class Config:
        extra = "forbid"


def _build_tenant_branding_response(tenant: Tenant) -> TenantBrandingResponse:
    return TenantBrandingResponse(
        slug=tenant.slug,
        company_name=tenant.company_name,
        reply_to_email=tenant.reply_to_email,
        support_email=tenant.support_email,
        admin_email=getattr(tenant, "admin_email", None),
        signature_name=tenant.signature_name,
    )


@router.get("/tenant", response_model=TenantBrandingResponse)
def get_my_tenant_branding(
    tenant_id: str = Depends(get_current_admin_tenant),
    db: Session = Depends(get_db),
):
    """
    Return the current admin's own tenant branding settings.

    NULL fields mean "use the RYZE default for this field" — the UI should
    show them as empty inputs with the RYZE fallback as placeholder text.
    """
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_id).first()
    if not tenant:
        # RYZE's own admins resolve to slug "ryze", which intentionally has no
        # tenants row. Surface a clear 404 rather than a 500.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant record for this account.",
        )
    return _build_tenant_branding_response(tenant)


@router.patch("/tenant", response_model=TenantBrandingResponse)
def update_my_tenant_branding(
    payload: TenantBrandingUpdate,
    tenant_id: str = Depends(get_current_admin_tenant),
    db: Session = Depends(get_db),
):
    """
    Update whitelisted branding fields on the current admin's own tenant.

    Uses exclude_unset so a PATCH only touches the fields actually sent —
    omitting a field leaves it unchanged; sending it as "" (empty string) is
    normalized to NULL, which restores the RYZE fallback for that field.
    """
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant record for this account.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # from_email is deliberately locked down: only a Resend-verified
        # domain may be a sender address, and tenants can't self-verify one
        # today. Kept on the request model (not a 422) so the still-deployed
        # frontend doesn't break; drop this skip once it stops sending the
        # field. Logged so journalctl surfaces any lingering attempts.
        if field == "from_email":
            logger.info(
                f"[settings] Ignored from_email in branding PATCH — slug={tenant.slug}"
            )
            continue
        # Normalize blank strings to NULL so clearing a field restores the
        # RYZE fallback rather than sending an empty "from" address.
        if isinstance(value, str):
            value = value.strip() or None
        setattr(tenant, field, value)

    db.commit()
    db.refresh(tenant)

    logger.info(
        f"[settings] Tenant branding updated — slug={tenant.slug} "
        f"fields={list(update_data.keys())}"
    )

    return _build_tenant_branding_response(tenant)
