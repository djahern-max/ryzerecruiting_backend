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
from sqlalchemy import text

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


def _cosine_search(db: Session, table_name: str, query_vector: list, limit: int):
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    sql = text(
        f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM {table_name}
        WHERE embedding IS NOT NULL
        ORDER BY distance
        LIMIT :limit
    """
    )
    rows = db.execute(sql, {"limit": limit}).fetchall()
    return rows


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------


@router.get("/candidates", response_model=List[CandidateSearchResult])
def search_candidates(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, "candidates", query_vector, limit)

    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    candidates = db.query(Candidate).filter(Candidate.id.in_(ids)).all()
    candidate_map = {c.id: c for c in candidates}

    return [
        CandidateSearchResult(
            id=candidate_map[id].id,
            name=candidate_map[id].name,
            current_title=candidate_map[id].current_title,
            current_company=candidate_map[id].current_company,
            location=candidate_map[id].location,
            ai_summary=candidate_map[id].ai_summary,
            ai_career_level=candidate_map[id].ai_career_level,
            ai_certifications=candidate_map[id].ai_certifications,
            ai_years_experience=candidate_map[id].ai_years_experience,
            score=round(max(0.0, 1.0 - float(distances[id])), 4),
        )
        for id in ids
        if id in candidate_map
    ]


@router.get("/employers", response_model=List[EmployerSearchResult])
def search_employers(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, "employer_profiles", query_vector, limit)
    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    employers = db.query(EmployerProfile).filter(EmployerProfile.id.in_(ids)).all()
    employer_map = {e.id: e for e in employers}

    return [
        EmployerSearchResult(
            id=employer_map[id].id,
            company_name=employer_map[id].company_name,
            ai_industry=employer_map[id].ai_industry,
            ai_company_overview=employer_map[id].ai_company_overview,
            relationship_status=employer_map[id].relationship_status,
            score=round(max(0.0, 1.0 - float(distances[id])), 4),
        )
        for id in ids
        if id in employer_map
    ]


@router.get("/job-orders", response_model=List[JobOrderSearchResult])
def search_job_orders(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, "job_orders", query_vector, limit)
    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    jobs = db.query(JobOrder).filter(JobOrder.id.in_(ids)).all()
    job_map = {j.id: j for j in jobs}

    return [
        JobOrderSearchResult(
            id=job_map[id].id,
            title=job_map[id].title,
            location=job_map[id].location,
            salary_min=job_map[id].salary_min,
            salary_max=job_map[id].salary_max,
            requirements=job_map[id].requirements,
            status=job_map[id].status,
            score=round(max(0.0, 1.0 - float(distances[id])), 4),
        )
        for id in ids
        if id in job_map
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
