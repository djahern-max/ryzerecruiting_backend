# app/schemas/oauth.py
from pydantic import BaseModel, EmailStr
from app.models.user import UserType


class OAuthUserComplete(BaseModel):
    """Schema for completing OAuth signup with user_type"""

    email: EmailStr
    oauth_provider: str
    oauth_provider_id: str
    user_type: UserType
    full_name: str | None = None
    avatar_url: str | None = None
