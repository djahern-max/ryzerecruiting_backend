# app/api/employer_profiles.py
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.models.employer_profile import EmployerProfile
from app.api.bookings import require_admin
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.employer_profile import (
    UpdateRecruiterNotes,
    EmployerProfileParseRequest,
    EmployerProfileParseResponse,
)
from app.services.ai_parser import parse_employer_prospect
from app.services.embedding_service import embed_employer_background


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/employer-profiles", tags=["employer-profiles"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_json_list(value) -> List[str]:
    """Safely parse a JSON string into a list. Returns [] on any failure."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _build_response(profile: EmployerProfile) -> "EmployerProfileResponse":
    return EmployerProfileResponse(
        id=profile.id,
        company_name=profile.company_name,
        website_url=profile.website_url,
        primary_contact_email=profile.primary_contact_email,
        phone=profile.phone,
        ai_industry=profile.ai_industry,
        ai_company_size=profile.ai_company_size,
        ai_company_overview=profile.ai_company_overview,
        ai_hiring_needs=_parse_json_list(profile.ai_hiring_needs),
        ai_talking_points=_parse_json_list(profile.ai_talking_points),
        ai_red_flags=profile.ai_red_flags,
        ai_brief_raw=profile.ai_brief_raw,
        ai_brief_updated_at=profile.ai_brief_updated_at,
        recruiter_notes=profile.recruiter_notes,
        relationship_status=profile.relationship_status,
        embedded_at=getattr(profile, "embedded_at", None),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


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
    ai_hiring_needs: Optional[List[str]] = None
    ai_talking_points: Optional[List[str]] = None
    ai_red_flags: Optional[str] = None
    ai_brief_raw: Optional[str] = None
    ai_brief_updated_at: Optional[datetime] = None

    # Recruiter-managed fields
    recruiter_notes: Optional[str] = None
    relationship_status: Optional[str] = None

    # Embedding status
    embedded_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=EmployerProfileResponse)
def get_my_employer_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the employer intelligence profile associated with the current user.
    Matches by primary_contact_email. Returns 404 if not yet set up.
    Available to authenticated employer users — no admin required.
    """
    profile = (
        db.query(EmployerProfile)
        .filter(EmployerProfile.primary_contact_email == current_user.email)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No employer profile found for this account.",
        )
    return _build_response(profile)


@router.get("/{profile_id}", response_model=EmployerProfileResponse)
def get_employer_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Fetch a single employer intelligence profile by ID.
    Admin only.
    """
    profile = db.query(EmployerProfile).filter(EmployerProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found.")
    return _build_response(profile)


@router.get("", response_model=List[EmployerProfileResponse])
def list_employer_profiles(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    List all employer intelligence profiles. Sorted newest first. Admin only.
    """
    profiles = (
        db.query(EmployerProfile)
        .order_by(EmployerProfile.created_at.desc())
        .all()
    )
    return [_build_response(p) for p in profiles]


@router.patch("/{profile_id}", response_model=EmployerProfileResponse)
def update_employer_profile(
    profile_id: int,
    payload: UpdateRecruiterNotes,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Update recruiter notes and/or relationship status on an employer profile.
    Admin only. Triggers a background re-embed after save.
    """
    profile = db.query(EmployerProfile).filter(EmployerProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    background_tasks.add_task(embed_employer_background, profile.id)

    return _build_response(profile)


@router.post("/parse", response_model=EmployerProfileParseResponse)
def parse_employer_profile(
    payload: EmployerProfileParseRequest,
    _: User = Depends(require_admin),
):
    """
    Parse raw employer/company text into structured profile fields.
    Admin only. Does NOT save — returns fields for review.
    """
    if not payload.text or len(payload.text.strip()) < 30:
        raise HTTPException(
            status_code=400,
            detail="Text is too short to parse.",
        )

    result = parse_employer_prospect(payload.text)
    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the provided text. Please try again.",
        )
    return result
