# app/schemas/employer_profile.py
from pydantic import BaseModel
from typing import Optional, List


class UpdateRecruiterNotes(BaseModel):
    recruiter_notes: Optional[str] = None
    relationship_status: Optional[str] = None


class EmployerProfileParseRequest(BaseModel):
    text: str


class EmployerProfileParseResponse(BaseModel):
    company_name: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = None
    website_url: Optional[str] = None
    hiring_role: Optional[str] = None
    ai_company_overview: Optional[str] = None
    ai_hiring_needs: Optional[List[str]] = None
    ai_talking_points: Optional[List[str]] = None
    ai_red_flags: Optional[str] = None
