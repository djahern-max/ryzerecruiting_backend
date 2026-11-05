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

def require_tenant(user: User) -> str:
    """
    Return the user's tenant slug, or raise 403 if the account has none.

    A NULL users.tenant_id grants no access to tenant-owned data. Use this in
    non-endpoint code that already holds a User; endpoints should depend on
    get_current_tenant / get_current_admin_tenant instead, which also enforce
    the tenant's billing state.
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not linked to a tenant.",
        )
    return user.tenant_id


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


def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


def _check_tenant_access(tenant_slug: str, db: Session) -> str:
    """
    Look up the tenant row and enforce trial / billing state.

    Returns the slug on success.
    Raises 403 if there is no tenants row for the slug — no row, no access.
    Raises 402 if the trial has expired or the subscription is cancelled.
    Tenants with billing_exempt=true skip the billing checks entirely.
    """
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant record for this account.",
        )

    if tenant.billing_exempt:
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
    Raises 403 if the user has no tenant_id or the tenant row is missing.

    Usage in an endpoint:
        @router.get("")
        def list_things(
            tenant_id: str = Depends(get_current_tenant),
            db: Session = Depends(get_db),
        ):
            return db.query(Thing).filter(Thing.tenant_id == tenant_id).all()
    """
    return _check_tenant_access(require_tenant(current_user), db)


def get_current_admin_tenant(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> str:
    """
    Same as get_current_tenant but also enforces admin-only access.
    Use this on every admin data endpoint going forward.
    """
    return _check_tenant_access(require_tenant(current_user), db)
