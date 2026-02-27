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
from app.schemas.employer_profile import UpdateRecruiterNotes

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

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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

    # Build dict manually so we can parse JSON strings BEFORE Pydantic validates.
    # Passing the ORM object directly to model_validate fails because
    # ai_hiring_needs and ai_talking_points are stored as raw JSON strings,
    # not Python lists — Pydantic rejects them at validation time.
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
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=List[EmployerProfileResponse])
def list_employer_profiles(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    List all employer profiles for RYZE Recruiting (tenant_id IS NULL).
    Sorted newest first. Admin only.
    """
    profiles = (
        db.query(EmployerProfile)
        .filter(EmployerProfile.tenant_id == None)
        .order_by(EmployerProfile.created_at.desc())
        .all()
    )

    result = []
    for profile in profiles:
        result.append(
            EmployerProfileResponse(
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
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        )
    return result


@router.patch("/{profile_id}", response_model=EmployerProfileResponse)
def update_employer_profile(
    profile_id: int,
    payload: UpdateRecruiterNotes,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Update recruiter notes and/or relationship status on an employer profile.
    Admin only.
    """
    profile = db.query(EmployerProfile).filter(EmployerProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found.")

    if payload.recruiter_notes is not None:
        profile.recruiter_notes = payload.recruiter_notes
    if payload.relationship_status is not None:
        profile.relationship_status = payload.relationship_status

    db.commit()
    db.refresh(profile)

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
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
