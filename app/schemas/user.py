# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class UserType(str, Enum):
    EMPLOYER = "EMPLOYER"
    CANDIDATE = "CANDIDATE"
    ADMIN = "ADMIN"


class PublicUserType(str, Enum):
    EMPLOYER = "EMPLOYER"
    CANDIDATE = "CANDIDATE"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    user_type: PublicUserType

    @field_validator("user_type")
    @classmethod
    def user_type_cannot_be_admin(cls, v):
        if v == "ADMIN":
            raise ValueError("Admin accounts cannot be created via registration.")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    user_type: UserType
    oauth_provider: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class TokenData(BaseModel):
    email: Optional[str] = None
