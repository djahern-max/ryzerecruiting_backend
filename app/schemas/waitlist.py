# app/schemas/waitlist.py
from pydantic import BaseModel, EmailStr


class WaitlistCreate(BaseModel):
    email: EmailStr
    source: str = "landing_page"
    intent: str | None = None  # "hiring" | "job_seeking" | "following"


class WaitlistResponse(BaseModel):
    id: int
    email: str
    source: str | None
    intent: str | None

    class Config:
        from_attributes = True
