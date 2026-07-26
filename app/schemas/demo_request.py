# app/schemas/demo_request.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class DemoRequestCreate(BaseModel):
    name: str
    company: str
    email: EmailStr
    phone: Optional[str] = None
    message: Optional[str] = None
    website: str = ""  # honeypot — real users never see or fill this field


class DemoRequestResponse(BaseModel):
    id: int
    name: str
    company: str
    email: str
    phone: Optional[str]
    message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
