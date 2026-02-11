# user.py - Schema definitions for user authentication and management
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# Base User Schema - shared properties
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


# Schema for user registration
class UserCreate(UserBase):
    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters"
    )


# Schema for user login
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Schema for token response
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Schema for token data (stored in JWT)
class TokenData(BaseModel):
    email: Optional[str] = None


# Schema for user response (without password)
class UserResponse(UserBase):
    id: int
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


# Schema for updating user info
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None


# Schema for password change
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(
        ..., min_length=8, description="New password must be at least 8 characters"
    )
