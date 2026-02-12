# app/schemas/user.py - Simplified schemas with email only
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for user registration - email and password only."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response (without password)."""

    id: int
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 syntax


class Token(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    token_type: str
    user: dict


class TokenData(BaseModel):
    """Schema for token payload data."""

    email: Optional[str] = None
