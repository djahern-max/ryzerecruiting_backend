# app/services/auth.py - Simplified authentication service
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin
from app.core.security import get_password_hash, verify_password, create_access_token


class AuthService:
    """
    Authentication service for user management.
    """

    @staticmethod
    def create_user(db: Session, user: UserCreate):
        """
        Create a new user with hashed password.
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

        # Create new user
        db_user = User(
            email=user.email, hashed_password=hashed_password, full_name=user.full_name
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return db_user

    @staticmethod
    def authenticate_user(db: Session, user: UserLogin):
        """
        Authenticate a user and return an access token.
        """
        # Find user by email
        db_user = db.query(User).filter(User.email == user.email).first()

        # Verify user exists and password is correct
        if not db_user or not verify_password(user.password, db_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create access token
        access_token = create_access_token(data={"sub": db_user.email})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": db_user.id,
                "email": db_user.email,
                "full_name": db_user.full_name,
            },
        }

    @staticmethod
    def get_user_by_email(db: Session, email: str):
        """
        Get a user by email.
        """
        return db.query(User).filter(User.email == email).first()
