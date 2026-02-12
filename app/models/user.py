# app/models/user.py - User model with user types and OAuth support
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from datetime import datetime
from app.core.database import Base
import enum


class UserType(str, enum.Enum):
    """User type enumeration - Employer or Candidate"""

    EMPLOYER = "employer"
    CANDIDATE = "candidate"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)  # Nullable for OAuth users
    user_type = Column(
        SQLEnum(UserType), nullable=False
    )  # Required: employer or candidate

    # OAuth fields
    oauth_provider = Column(String, nullable=True)  # "google", "linkedin", or None
    oauth_provider_id = Column(String, nullable=True)  # Provider's unique user ID

    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
