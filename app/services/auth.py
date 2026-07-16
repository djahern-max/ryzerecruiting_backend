# app/services/auth.py - Authentication service with user_type support
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import Optional
from app.models.user import User, UserType
from app.schemas.user import UserCreate, UserLogin
from app.core.security import get_password_hash, verify_password, create_access_token
from app.services.branding import get_branding


class AuthService:
    """
    Authentication service for user management.
    """

    @staticmethod
    def create_user(db: Session, user: UserCreate):
        """
        Create a new user with hashed password and user_type.
        Email serves as the unique identifier.
        Note: UserCreate schema uses PublicUserType — admin cannot be registered here.
        """
        existing_user = db.query(User).filter(User.email == user.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        hashed_password = get_password_hash(user.password)

        # Lazy import: app.core.deps imports AuthService before defining
        # RYZE_TENANT, so importing tenant_resolution (which imports
        # RYZE_TENANT from deps) at module load time would cycle back here.
        from app.services.tenant_resolution import resolve_signup_tenant

        # user.user_type is PublicUserType (schema enum), compared inside
        # resolve_signup_tenant against models.user.UserType — both mix in
        # str so cross-class equality works by value. Intentional, not a bug.
        tenant_id = resolve_signup_tenant(db, user.email, user.user_type)

        db_user = User(
            email=user.email,
            hashed_password=hashed_password,
            full_name=user.full_name,
            user_type=user.user_type,
            tenant_id=tenant_id,
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return db_user

    @staticmethod
    def _auth_user_payload(db: Session, user: User) -> dict:
        """
        Shared shape for the `user` key returned by login and OAuth signup
        completion, so the two sites can't drift. Resolves tenant branding
        via the existing resolver (app/services/branding.py) — no new
        branding logic here.
        """
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "user_type": user.user_type.value,
            "is_superuser": user.is_superuser,
            "tenant_id": user.tenant_id,
            "tenant_brand_name": get_branding(db, user.tenant_id).brand_name,
        }

    @staticmethod
    def authenticate_user(db: Session, user: UserLogin):
        db_user = db.query(User).filter(User.email == user.email).first()

        if not db_user or not verify_password(user.password, db_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(data={"sub": db_user.email})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": AuthService._auth_user_payload(db, db_user),
        }

    @staticmethod
    def get_user_by_email(db: Session, email: str):
        """
        Get a user by email.
        """
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_or_create_oauth_user(
        db: Session,
        email: str,
        oauth_provider: str,
        oauth_provider_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        user_type: Optional[UserType] = None,
    ) -> tuple[User, bool]:
        """
        Get existing OAuth user or create a new one.
        Returns (user, is_new) tuple.
        Note: OAuth flow only allows employer/candidate — admin cannot be created via OAuth.
        """
        # Check if user exists with this OAuth provider
        user = (
            db.query(User)
            .filter(
                User.oauth_provider == oauth_provider,
                User.oauth_provider_id == oauth_provider_id,
            )
            .first()
        )

        if user:
            # Existing OAuth user — update info
            if full_name:
                user.full_name = full_name
            if avatar_url:
                user.avatar_url = avatar_url
            db.commit()
            db.refresh(user)
            return user, False

        # Check if email exists (user might have signed up with password)
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered with password login. Please use password login.",
            )

        if user_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User type is required for new users",
            )

        # Prevent admin accounts from being created via OAuth
        if user_type == UserType.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin accounts cannot be created via OAuth.",
            )

        # Lazy import — see create_user() above for why this can't be a
        # module-level import.
        from app.services.tenant_resolution import resolve_signup_tenant

        tenant_id = resolve_signup_tenant(db, email, user_type)

        # Create new OAuth user
        new_user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            user_type=user_type,
            hashed_password=None,
            tenant_id=tenant_id,
            first_login_at=datetime.now(timezone.utc),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user, True

    @staticmethod
    def complete_oauth_signup(
        db: Session,
        email: str,
        oauth_provider: str,
        oauth_provider_id: str,
        user_type: UserType,
    ) -> User:
        """
        Complete OAuth signup by setting user_type for a pending OAuth user.
        Called after user selects employer/candidate.
        """
        user, is_new = AuthService.get_or_create_oauth_user(
            db=db,
            email=email,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            user_type=user_type,
        )
        return user
