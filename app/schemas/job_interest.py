# app/schemas/job_interest.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class JobInterestCreate(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class JobInterestResponse(BaseModel):
    job_order_id: int
    created_at: datetime

    class Config:
        from_attributes = True
