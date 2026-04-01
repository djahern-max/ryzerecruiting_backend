# app/core/deps.py
# Shared FastAPI dependencies.
# EP16: Added get_current_tenant — extracts the tenant_id from the authenticated
#       user so every endpoint can scope its queries without reading the user model twice.
# EP17: get_current_tenant now enforces trial and billing state.
#       Expired trial or cancelled subscription raises 402 Payment Required.

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.services.auth import AuthService
from app.models.user import User, UserType
from app.models.tenant import Tenant

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Default tenant slug — RYZE Recruiting's own data
RYZE_TENANT = "ryze"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user = AuthService.get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.user_type != UserType.ADMIN and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ---------------------------------------------------------------------------
# EP16 — Multi-tenant dependency
# EP17 — Now enforces trial and billing state
# ---------------------------------------------------------------------------


def _check_tenant_access(tenant_slug: str, db: Session) -> str:
    """
    Look up the tenant row and enforce trial / billing state.

    RYZE's own tenant slug bypasses billing checks — it is always active.

    Returns the slug on success.
    Raises 402 if the trial has expired or the subscription is cancelled.
    """
    if tenant_slug == RYZE_TENANT:
        return tenant_slug

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()

    # No tenants row yet means this is a legacy or pre-EP17 account — allow through.
    if tenant is None:
        return tenant_slug

    now = datetime.now(timezone.utc)

    if tenant.status == "active":
        # Paying subscriber — full access
        return tenant_slug

    if tenant.status == "trial":
        if tenant.trial_ends_at and tenant.trial_ends_at > now:
            # Trial is still running — full access
            return tenant_slug
        # Trial has expired
        raise HTTPException(
            status_code=402,
            detail="Trial expired. Please upgrade to continue.",
        )

    # expired | cancelled
    raise HTTPException(
        status_code=402,
        detail="Subscription inactive. Please upgrade to continue.",
    )


def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    """
    Extract the tenant slug from the authenticated user and enforce
    trial / billing state.

    All data endpoints depend on this to scope their queries.
    Falls back to RYZE_TENANT for legacy rows where tenant_id is NULL.

    Usage in an endpoint:
        @router.get("")
        def list_things(
            tenant_id: str = Depends(get_current_tenant),
            db: Session = Depends(get_db),
        ):
            return db.query(Thing).filter(Thing.tenant_id == tenant_id).all()
    """
    slug = current_user.tenant_id or RYZE_TENANT
    return _check_tenant_access(slug, db)


def get_current_admin_tenant(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> str:
    """
    Same as get_current_tenant but also enforces admin-only access.
    Use this on every admin data endpoint going forward.
    """
    slug = current_user.tenant_id or RYZE_TENANT
    return _check_tenant_access(slug, db)
