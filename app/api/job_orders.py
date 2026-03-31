# app/api/job_orders.py
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from app.core.database import get_db
from app.models.job_order import JobOrder
from app.models.candidate import Candidate
from app.api.bookings import require_admin
from app.core.deps import get_current_user
from app.models.user import User, UserType
from app.schemas.job_order import (
    JobOrderCreate,
    JobOrderUpdate,
    JobOrderResponse,
    JobOrderParseRequest,
    JobOrderParseResponse,
)
from app.services.ai_parser import parse_job_description
from app.services.embedding_service import embed_job_order_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-orders", tags=["job-orders"])


# ---------------------------------------------------------------------------
# Inline response schema for EP15 employer candidate-matching endpoint
# ---------------------------------------------------------------------------


class CandidateMatchResult(BaseModel):
    """
    Employer-safe candidate view — no contact info exposed.
    Name is anonymized as "First L." format.
    """

    display_name: str
    current_title: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_years_experience: Optional[int] = None
    match_score: float

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Public endpoint
# ---------------------------------------------------------------------------


@router.get("/open", response_model=List[JobOrderResponse])
def list_open_job_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id or "ryze"
    return (
        db.query(JobOrder)
        .filter(JobOrder.status == "open", JobOrder.tenant_id == tenant_id)
        .order_by(JobOrder.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# EP15 — Employer-facing candidate match endpoint
# IMPORTANT: defined before /{job_order_id} so FastAPI doesn't swallow it.
# ---------------------------------------------------------------------------


@router.get(
    "/{job_order_id}/candidate-matches", response_model=List[CandidateMatchResult]
)
def get_candidate_matches_for_job(
    job_order_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    EP15 — Returns top candidates ranked by AI match score for a given job order.

    Uses the job order's pgvector embedding as the query vector against
    the candidates table. Returns results sorted best-match-first.

    Candidate names are anonymized as "First L." — contact info is
    never exposed. Employers see enough to understand the pipeline quality
    and engage RYZE to proceed.

    Available to: authenticated employer and admin users.
    """
    is_employer = current_user.user_type == UserType.EMPLOYER
    is_admin = current_user.is_superuser

    if not (is_employer or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Employer or admin access required.",
        )

    tenant_id = current_user.tenant_id or "ryze"  # EP16

    job = (
        db.query(JobOrder)
        .filter(
            JobOrder.id == job_order_id,
            JobOrder.tenant_id == tenant_id,  # EP16
        )
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job order not found.")

    if job.embedding is None:
        logger.info(
            f"Job order #{job_order_id} ({job.title}) has no embedding — "
            "returning empty candidate matches."
        )
        return []

    # Run cosine similarity: job embedding vs candidates table
    try:
        vector_str = "[" + ",".join(str(v) for v in job.embedding) + "]"
        sql = text(
            f"""
            SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
            FROM candidates
            WHERE embedding IS NOT NULL
              AND tenant_id = :tenant_id
            ORDER BY distance
            LIMIT :limit
            """
        )
        rows = db.execute(
            sql, {"tenant_id": tenant_id, "limit": limit}
        ).fetchall()  # EP16
    except Exception as e:
        logger.error(f"Cosine search failed for job order #{job_order_id}: {e}")
        return []

    if not rows:
        return []

    ids = [r[0] for r in rows]
    distances = {r[0]: float(r[1]) for r in rows}

    candidates = (
        db.query(Candidate)
        .filter(
            Candidate.id.in_(ids),
            Candidate.tenant_id == tenant_id,  # EP16
        )
        .all()
    )
    candidate_map = {c.id: c for c in candidates}

    results = [] @ router.get("", response_model=List[JobOrderResponse])
    for cid in ids:
        if cid not in candidate_map:
            continue
        c = candidate_map[cid]

        # Anonymize: "Sarah Chen" → "Sarah C."
        name_parts = (c.name or "Candidate").split()
        display_name = (
            f"{name_parts[0]} {name_parts[-1][0]}."
            if len(name_parts) > 1
            else name_parts[0]
        )

        results.append(
            CandidateMatchResult(
                display_name=display_name,
                current_title=c.current_title,
                ai_career_level=c.ai_career_level,
                ai_certifications=c.ai_certifications,
                ai_years_experience=c.ai_years_experience,
                match_score=round(max(0.0, 1.0 - distances[cid]), 4),
            )
        )

    logger.info(
        f"Job order #{job_order_id} candidate matches: {len(results)} results "
        f"(top score: {results[0].match_score if results else 'n/a'})"
    )
    return results


# ---------------------------------------------------------------------------
# Admin CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[JobOrderResponse])
def list_job_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or "ryze"
    return (
        db.query(JobOrder)
        .filter(JobOrder.tenant_id == tenant_id)
        .order_by(JobOrder.created_at.desc())
        .all()
    )


@router.get("/{job_order_id}", response_model=JobOrderResponse)
def get_job_order(
    job_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or "ryze"
    job = (
        db.query(JobOrder)
        .filter(
            JobOrder.id == job_order_id,
            JobOrder.tenant_id == tenant_id,
        )
        .first()
    )
    tenant_id = current_user.tenant_id or "ryze"
    job = (
        db.query(JobOrder)
        .filter(
            JobOrder.id == job_order_id,
            JobOrder.tenant_id == tenant_id,
        )
        .first()
    )
    job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    return job_order


@router.post("", response_model=JobOrderResponse, status_code=status.HTTP_201_CREATED)
def create_job_order(
    payload: JobOrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = JobOrder(**payload.model_dump())
    db.add(job_order)
    db.commit()
    db.refresh(job_order)
    logger.info(f"Job order created: {job_order.title} (#{job_order.id})")
    background_tasks.add_task(embed_job_order_background, job_order.id)
    return job_order


@router.patch("/{job_order_id}", response_model=JobOrderResponse)
def update_job_order(
    job_order_id: int,
    payload: JobOrderUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job_order, field, value)

    job_order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job_order)
    background_tasks.add_task(embed_job_order_background, job_order.id)
    return job_order


@router.delete("/{job_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_order(
    job_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    db.delete(job_order)
    db.commit()


# ---------------------------------------------------------------------------
# Parse (admin only)
# ---------------------------------------------------------------------------


@router.post("/parse", response_model=JobOrderParseResponse)
def parse_job_order(
    payload: JobOrderParseRequest,
    _: User = Depends(require_admin),
):
    if not payload.text or len(payload.text.strip()) < 30:
        raise HTTPException(
            status_code=400,
            detail="Text is too short to parse.",
        )
    result = parse_job_description(payload.text)
    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the provided text. Please try again.",
        )
    return result
