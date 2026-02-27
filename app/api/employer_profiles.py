# app/api/employer_profiles.py
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.models.employer_profile import EmployerProfile
from app.api.bookings import require_admin
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/employer-profiles", tags=["employer-profiles"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class EmployerProfileResponse(BaseModel):
    id: int
    company_name: str
    website_url: Optional[str] = None
    primary_contact_email: Optional[str] = None
    phone: Optional[str] = None

    # AI intelligence fields
    ai_industry: Optional[str] = None
    ai_company_size: Optional[str] = None
    ai_company_overview: Optional[str] = None
    ai_hiring_needs: Optional[List[str]] = None  # Parsed from JSON string
    ai_talking_points: Optional[List[str]] = None  # Parsed from JSON string
    ai_red_flags: Optional[str] = None
    ai_brief_raw: Optional[str] = None
    ai_brief_updated_at: Optional[datetime] = None

    # Recruiter-managed fields
    recruiter_notes: Optional[str] = None
    relationship_status: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{profile_id}", response_model=EmployerProfileResponse)
def get_employer_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Fetch a single employer intelligence profile by ID.
    Admin only. Used by the admin dashboard to render the AI brief panel.
    """
    profile = db.query(EmployerProfile).filter(EmployerProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found.")

    # Parse JSON arrays from stored strings
    result = EmployerProfileResponse.model_validate(profile)
    if profile.ai_hiring_needs:
        try:
            result.ai_hiring_needs = json.loads(profile.ai_hiring_needs)
        except (json.JSONDecodeError, TypeError):
            result.ai_hiring_needs = []

    if profile.ai_talking_points:
        try:
            result.ai_talking_points = json.loads(profile.ai_talking_points)
        except (json.JSONDecodeError, TypeError):
            result.ai_talking_points = []

    return result
