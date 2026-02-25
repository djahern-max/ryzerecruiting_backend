# app/schemas/user.py - User schemas with user_type support
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class UserType(str, Enum):
    """User type enumeration — mirrors the model enum"""

    EMPLOYER = "employer"
    CANDIDATE = "candidate"
    ADMIN = "admin"


class PublicUserType(str, Enum):
    """
    Restricted enum for public-facing registration.
    Prevents anyone from self-registering as an admin.
    """

    EMPLOYER = "employer"
    CANDIDATE = "candidate"


class UserCreate(BaseModel):
    """Schema for user registration — only employer/candidate allowed publicly."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    user_type: PublicUserType  # Restricted: cannot register as admin

    @field_validator("user_type")
    @classmethod
    def user_type_cannot_be_admin(cls, v):
        if v == "admin":
            raise ValueError("Admin accounts cannot be created via registration.")
        return v


class UserLogin(BaseModel):
    """Schema for user login"""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response (without password)"""

    id: int
    email: EmailStr
    full_name: Optional[str]
    user_type: UserType  # Full enum including admin for responses
    oauth_provider: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2


class Token(BaseModel):
    """Schema for JWT token response"""

    access_token: str
    token_type: str
    user: dict


class TokenData(BaseModel):
    """Schema for token payload data"""

    email: Optional[str] = None
