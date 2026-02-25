# app/services/auth.py - Authentication service with user_type support
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import Optional
from app.models.user import User, UserType
from app.schemas.user import UserCreate, UserLogin
from app.core.security import get_password_hash, verify_password, create_access_token


class AuthService:
    """
    Authentication service for user management.
    """

    @staticmethod
    def create_user(db: Session, user: UserCreate):
        """
        Create a new user with hashed password and user_type.
        Email serves as the unique identifier.
        """
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == user.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Hash the password (safely truncated to 72 bytes)
        hashed_password = get_password_hash(user.password)

        # Create new user with user_type
        db_user = User(
            email=user.email,
            hashed_password=hashed_password,
            full_name=user.full_name,
            user_type=user.user_type,  # NEW: Store user type (employer/candidate)
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return db_user

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
            "user": {
                "id": db_user.id,
                "email": db_user.email,
                "full_name": db_user.full_name,
                "user_type": db_user.user_type.value,
                "is_superuser": db_user.is_superuser,  # ← added
            },
        }

    @staticmethod
    def get_user_by_email(db: Session, email: str):
        """
        Get a user by email.
        """
        return db.query(User).filter(User.email == email).first()

    # NEW: OAuth-specific methods
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
        Get existing OAuth user or create incomplete one.
        Returns (user, is_new) tuple.

        If user_type is None, creates an incomplete user that needs user_type selection.
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
            # Existing OAuth user - update info
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

        # user_type is required for new users - this will fail if None
        if user_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User type is required for new users",
            )

        # Create new OAuth user
        new_user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            user_type=user_type,
            hashed_password=None,  # OAuth users don't have passwords
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
        This is called after the user selects employer/candidate.
        """
        # Verify the OAuth data matches before creating
        user, is_new = AuthService.get_or_create_oauth_user(
            db=db,
            email=email,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            user_type=user_type,
        )
        return user
