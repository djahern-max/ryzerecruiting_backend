# app/core/deps.py
# Shared FastAPI dependencies.
# EP16: Added get_current_tenant — extracts the tenant_id from the authenticated
# user so every endpoint can scope its queries without reading the user model twice.

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.services.auth import AuthService
from app.models.user import User, UserType

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
# ---------------------------------------------------------------------------

def get_current_tenant(current_user: User = Depends(get_current_user)) -> str:
    """
    Extract the tenant slug from the authenticated user.

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
    return current_user.tenant_id or RYZE_TENANT


def get_current_admin_tenant(
    current_user: User = Depends(get_current_admin_user),
) -> str:
    """
    Same as get_current_tenant but also enforces admin-only access.
    Use this on every admin data endpoint going forward.
    """
    return current_user.tenant_id or RYZE_TENANT
