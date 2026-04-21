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
    source: Optional[str] = "manual"


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
    tenant_id: Optional[str] = None
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
    # EP17 candidate flow fields
    source: Optional[str] = "manual"
    meeting_transcript: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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


class CandidateSelfUpdate(BaseModel):
    """
    Fields a candidate is allowed to update on their own profile.
    Recruiter-owned fields (AI fields, notes, source, etc.) are excluded.
    """

    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    class Config:
        extra = "forbid"
