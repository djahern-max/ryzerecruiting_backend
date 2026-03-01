# app/schemas/waitlist.py
from pydantic import BaseModel, EmailStr


class WaitlistCreate(BaseModel):
    email: EmailStr
    source: str = "landing_page"


class WaitlistResponse(BaseModel):
    id: int
    email: str
    source: str | None

    class Config:
        from_attributes = True
