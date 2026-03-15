# app/api/candidates.py
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.models.candidate import Candidate
from app.api.bookings import require_admin
from app.models.user import User
from app.schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateResponse,
    CandidateParseRequest,
    CandidateParseResponse,
)
from app.services.ai_parser import parse_candidate_profile
from app.services.embedding_service import embed_candidate_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.get("", response_model=List[CandidateResponse])
def list_candidates(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(Candidate).filter(Candidate.tenant_id == 1)

    if search:
        term = f"%{search}%"
        query = query.filter(
            Candidate.name.ilike(term)
            | Candidate.email.ilike(term)
            | Candidate.current_title.ilike(term)
            | Candidate.current_company.ilike(term)
            | Candidate.location.ilike(term)
        )

    return query.order_by(Candidate.created_at.desc()).all()


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == 1)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return candidate


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    candidate = Candidate(
        tenant_id=1,
        **payload.model_dump(),
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    logger.info(f"Candidate created: {candidate.name} (#{candidate.id})")

    # Auto-embed in background — non-blocking
    background_tasks.add_task(embed_candidate_background, candidate.id)

    return candidate


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == 1)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(candidate, field, value)

    # Clear old embedding so the record shows as pending until the new one lands
    candidate.embedding = None
    candidate.embedded_at = None
    candidate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(candidate)

    # Re-embed with updated content
    background_tasks.add_task(embed_candidate_background, candidate.id)

    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == 1)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    db.delete(candidate)
    db.commit()


@router.post("/parse", response_model=CandidateParseResponse)
def parse_candidate(
    payload: CandidateParseRequest,
    _: User = Depends(require_admin),
):
    """
    Parse a LinkedIn profile paste or resume text.
    Returns structured fields for review — does NOT save to database.
    """
    if not payload.text or len(payload.text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Text is too short to parse. Please paste the full profile or resume.",
        )

    result = parse_candidate_profile(payload.text)

    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the provided text. Please try again.",
        )

    return result
