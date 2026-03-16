# app/schemas/candidate.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CandidateCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_raw_text: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_experience: Optional[str] = None
    ai_education: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_skills: Optional[List[str]] = None
    ai_years_experience: Optional[int] = None
    notes: Optional[str] = None


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_raw_text: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_experience: Optional[str] = None
    ai_education: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_skills: Optional[List[str]] = None
    ai_years_experience: Optional[int] = None
    ai_outreach_message: Optional[str] = None
    notes: Optional[str] = None


class CandidateResponse(BaseModel):
    id: int
    tenant_id: Optional[str] = None  # String(100) — was int, now consistent
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_raw_text: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_experience: Optional[str] = None
    ai_education: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_skills: Optional[List[str]] = None
    ai_years_experience: Optional[int] = None
    ai_outreach_message: Optional[str] = None
    ai_parsed_at: Optional[datetime] = None
    embedded_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CandidateParseRequest(BaseModel):
    text: str


class CandidateParseResponse(BaseModel):
    name: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_experience: Optional[str] = None
    ai_education: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_skills: Optional[List[str]] = None
    ai_years_experience: Optional[int] = None
