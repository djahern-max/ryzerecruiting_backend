# app/api/search.py
"""
Semantic search endpoints for RYZE.ai RAG functionality.

All search uses cosine similarity via PGVector (<=> operator).
Score returned is 0-1 where 1 = identical, 0 = unrelated.
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.bookings import require_admin
from app.models.user import User
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.services.embedding_service import generate_embedding, sync_embeddings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CandidateSearchResult(BaseModel):
    id: int
    name: str
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_years_experience: Optional[int] = None
    score: float

    class Config:
        from_attributes = True


class EmployerSearchResult(BaseModel):
    id: int
    company_name: str
    ai_industry: Optional[str] = None
    ai_company_overview: Optional[str] = None
    relationship_status: Optional[str] = None
    score: float

    class Config:
        from_attributes = True


class JobOrderSearchResult(BaseModel):
    id: int
    title: str
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    status: str
    score: float

    class Config:
        from_attributes = True


class SyncResponse(BaseModel):
    candidates: int
    employers: int
    job_orders: int
    errors: int
    message: str


# ---------------------------------------------------------------------------
# Helper — run cosine search against a model
# ---------------------------------------------------------------------------

def _cosine_search(db: Session, model, query_vector: list, limit: int):
    """
    Returns (record, distance) pairs ordered by cosine distance ascending.
    Lower distance = more similar. We convert to score = 1 - distance.
    """
    results = (
        db.query(model, model.embedding.op("<=>")(query_vector).label("distance"))
        .filter(model.embedding.isnot(None))
        .order_by("distance")
        .limit(limit)
        .all()
    )
    return results


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------

@router.get("/candidates", response_model=List[CandidateSearchResult])
def search_candidates(
    q: str = Query(..., min_length=3, description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Semantic search over candidates using vector similarity.
    Example: "senior CPA with public accounting Big 4 experience in Boston"
    """
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, Candidate, query_vector, limit)

    if not rows:
        return []

    return [
        CandidateSearchResult(
            id=candidate.id,
            name=candidate.name,
            current_title=candidate.current_title,
            current_company=candidate.current_company,
            location=candidate.location,
            ai_summary=candidate.ai_summary,
            ai_career_level=candidate.ai_career_level,
            ai_certifications=candidate.ai_certifications,
            ai_years_experience=candidate.ai_years_experience,
            score=round(max(0.0, 1.0 - float(distance)), 4),
        )
        for candidate, distance in rows
    ]


@router.get("/employers", response_model=List[EmployerSearchResult])
def search_employers(
    q: str = Query(..., min_length=3, description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Semantic search over employer profiles.
    Example: "manufacturing company needing cost accountants in New England"
    """
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, EmployerProfile, query_vector, limit)

    return [
        EmployerSearchResult(
            id=employer.id,
            company_name=employer.company_name,
            ai_industry=employer.ai_industry,
            ai_company_overview=employer.ai_company_overview,
            relationship_status=employer.relationship_status,
            score=round(max(0.0, 1.0 - float(distance)), 4),
        )
        for employer, distance in rows
    ]


@router.get("/job-orders", response_model=List[JobOrderSearchResult])
def search_job_orders(
    q: str = Query(..., min_length=3, description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Semantic search over open job orders.
    Example: "controller role 150k remote with NetSuite experience"
    """
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, JobOrder, query_vector, limit)

    return [
        JobOrderSearchResult(
            id=job.id,
            title=job.title,
            location=job.location,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            requirements=job.requirements,
            status=job.status,
            score=round(max(0.0, 1.0 - float(distance)), 4),
        )
        for job, distance in rows
    ]


# ---------------------------------------------------------------------------
# Admin — trigger embedding sync on demand
# ---------------------------------------------------------------------------

@router.post("/embeddings/sync", response_model=SyncResponse)
def trigger_embedding_sync(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    """
    Admin endpoint: kick off embedding generation for all unembedded records.
    Runs in the background — returns immediately with a confirmation.
    Check server logs for progress.
    """
    background_tasks.add_task(_run_sync_and_log)
    return SyncResponse(
        candidates=0,
        employers=0,
        job_orders=0,
        errors=0,
        message="Embedding sync started in background. Check server logs for progress.",
    )


@router.post("/embeddings/sync/blocking", response_model=SyncResponse)
def trigger_embedding_sync_blocking(
    _: User = Depends(require_admin),
):
    """
    Admin endpoint: run embedding sync synchronously and return counts.
    Useful for testing — blocks until complete.
    """
    try:
        counts = sync_embeddings(batch_size=100)
        return SyncResponse(
            **counts,
            message=(
                f"Sync complete. Embedded: {counts['candidates']} candidates, "
                f"{counts['employers']} employers, {counts['job_orders']} job orders. "
                f"Errors: {counts['errors']}."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


def _run_sync_and_log():
    """Background task wrapper with error logging."""
    try:
        counts = sync_embeddings(batch_size=100)
        logger.info(f"Background embedding sync complete: {counts}")
    except Exception as e:
        logger.error(f"Background embedding sync failed: {e}")
