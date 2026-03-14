# app/schemas/job_order.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class JobOrderCreate(BaseModel):
    employer_profile_id: Optional[int] = None
    title: str
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "open"


class JobOrderUpdate(BaseModel):
    employer_profile_id: Optional[int] = None
    title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    filled_at: Optional[datetime] = None


class JobOrderResponse(BaseModel):
    id: int
    tenant_id: int
    employer_profile_id: Optional[int] = None
    title: str
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    filled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobOrderParseRequest(BaseModel):
    text: str


class JobOrderParseResponse(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    company_name: Optional[str] = None
    notes: Optional[str] = None
