# app/api/employer_profiles.py
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, RYZE_TENANT
from app.models.employer_profile import EmployerProfile
from app.models.user import User
from app.api.bookings import require_admin
from app.api.auth import get_current_user as get_any_authenticated_user
from app.schemas.employer_profile import (
    UpdateRecruiterNotes,
    EmployerProfileParseRequest,
    EmployerProfileParseResponse,
)
from app.services.ai_parser import parse_employer_prospect
from app.services.embedding_service import embed_employer_background
from app.services.spaces import upload_file, delete_file, make_unique_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/employer-profiles", tags=["employer-profiles"])


# ---------------------------------------------------------------------------
# Helper — resolve the employer profile that belongs to the current user.
# Matches by primary_contact_email AND tenant_id for strict isolation.
# ---------------------------------------------------------------------------


def _resolve_employer_for_user(
    db: Session, current_user: User
) -> Optional[EmployerProfile]:
    tenant_id = current_user.tenant_id or RYZE_TENANT
    return (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.primary_contact_email == current_user.email,
            EmployerProfile.tenant_id == tenant_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Helper — safely parse JSON list fields
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

    # EP19 — profile images
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None

    # Embedding status
    embedded_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Self-edit schema — whitelist only fields the employer may touch
# ---------------------------------------------------------------------------


class EmployerSelfUpdate(BaseModel):
    """
    Fields an employer user is allowed to edit on their own profile.
    Recruiter-owned fields (red flags, notes, relationship status, AI raw brief)
    are intentionally excluded.
    """

    company_name: Optional[str] = None
    website_url: Optional[str] = None
    phone: Optional[str] = None
    ai_industry: Optional[str] = None
    ai_company_size: Optional[str] = None
    ai_company_overview: Optional[str] = None

    class Config:
        extra = "forbid"


# ---------------------------------------------------------------------------
# _build_response helper
# ---------------------------------------------------------------------------


def _build_response(profile: EmployerProfile) -> EmployerProfileResponse:
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
        logo_url=getattr(profile, "logo_url", None),
        banner_url=getattr(profile, "banner_url", None),
        embedded_at=getattr(profile, "embedded_at", None),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ---------------------------------------------------------------------------
# /me routes — MUST come before /{profile_id} to avoid FastAPI treating
# the literal string "me" as an integer path parameter.
# ---------------------------------------------------------------------------


@router.get("/me", response_model=EmployerProfileResponse)
def get_my_employer_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Returns the employer intelligence profile associated with the current user.
    Matches by primary_contact_email AND tenant_id.
    Available to any authenticated user — no admin required.
    """
    profile = _resolve_employer_for_user(db, current_user)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No employer profile found for this account.",
        )
    return _build_response(profile)


@router.patch("/me", response_model=EmployerProfileResponse)
def update_my_employer_profile(
    payload: EmployerSelfUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Allows an employer to edit their own company profile.
    Whitelisted fields only — recruiter-owned fields are not writable here.
    Triggers a background re-embed after save.
    """
    profile = _resolve_employer_for_user(db, current_user)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No employer profile found for this account.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    background_tasks.add_task(embed_employer_background, profile.id)

    return _build_response(profile)


@router.post("/me/logo")
async def upload_my_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Upload (or replace) the company logo for the current employer's profile.
    Stored at employers/{id}/logo in DO Spaces.
    Recommended: square or landscape image, max 5MB.
    """
    profile = _resolve_employer_for_user(db, current_user)
    if not profile:
        raise HTTPException(status_code=404, detail="No employer profile found.")

    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB).")

    # Delete the old logo from Spaces if one exists
    if getattr(profile, "logo_url", None):
        old_key = profile.logo_url.replace(
            settings.DO_SPACES_CDN_BASE.rstrip("/") + "/", ""
        )
        delete_file(old_key)

    unique_name = make_unique_filename(file.filename or "logo.jpg")
    cdn_url = upload_file(
        data,
        f"employers/{profile.id}/logo",
        unique_name,
        file.content_type,
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Logo upload failed.")

    profile.logo_url = cdn_url
    db.commit()
    return {"logo_url": cdn_url}


@router.post("/me/banner")
async def upload_my_banner(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Upload (or replace) the banner image for the current employer's profile.
    Stored at employers/{id}/banner in DO Spaces.
    Max 10MB.
    """
    profile = _resolve_employer_for_user(db, current_user)
    if not profile:
        raise HTTPException(status_code=404, detail="No employer profile found.")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    # Delete the old banner from Spaces if one exists
    if getattr(profile, "banner_url", None):
        old_key = profile.banner_url.replace(
            settings.DO_SPACES_CDN_BASE.rstrip("/") + "/", ""
        )
        delete_file(old_key)

    unique_name = make_unique_filename(file.filename or "banner.jpg")
    cdn_url = upload_file(
        data,
        f"employers/{profile.id}/banner",
        unique_name,
        file.content_type,
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Banner upload failed.")

    profile.banner_url = cdn_url
    db.commit()
    return {"banner_url": cdn_url}


# ---------------------------------------------------------------------------
# Admin endpoints — /{profile_id} routes AFTER /me routes
# ---------------------------------------------------------------------------


@router.get("", response_model=List[EmployerProfileResponse])
def list_employer_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or RYZE_TENANT
    profiles = (
        db.query(EmployerProfile)
        .filter(EmployerProfile.tenant_id == tenant_id)
        .order_by(EmployerProfile.created_at.desc())
        .all()
    )
    return [_build_response(p) for p in profiles]


@router.get("/{profile_id}", response_model=EmployerProfileResponse)
def get_employer_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Fetch a single employer intelligence profile by ID.
    Admin only.
    """
    tenant_id = current_user.tenant_id or RYZE_TENANT
    profile = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.id == profile_id,
            EmployerProfile.tenant_id == tenant_id,
        )
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found.")
    return _build_response(profile)


@router.patch("/{profile_id}", response_model=EmployerProfileResponse)
def update_employer_profile(
    profile_id: int,
    payload: UpdateRecruiterNotes,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update recruiter notes and/or relationship status on an employer profile.
    Admin only. Triggers a background re-embed after save.
    """
    tenant_id = current_user.tenant_id or RYZE_TENANT
    profile = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.id == profile_id,
            EmployerProfile.tenant_id == tenant_id,
        )
        .first()
    )
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
