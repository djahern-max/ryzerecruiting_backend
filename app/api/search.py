# app/api/search.py
# EP16: All cosine searches now scope to the requesting admin's tenant_id.
# _cosine_search() now accepts an optional tenant_id and adds a WHERE clause
# so vector similarity queries never leak records across firm boundaries.

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_admin_user, get_current_admin_tenant, RYZE_TENANT
from app.models.user import User
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.services.embedding_service import generate_embedding, sync_embeddings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

# Convenience alias
require_admin = get_current_admin_user


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
# EP16: Tenant-aware cosine search helper
# ---------------------------------------------------------------------------


def _cosine_search(
    db: Session,
    table_name: str,
    query_vector: list,
    limit: int,
    tenant_id: str = RYZE_TENANT,  # EP16: new param, defaults to "ryze"
):
    """
    Run a cosine similarity search via PGVector.

    EP16 change: adds WHERE tenant_id = :tenant_id so results are always
    scoped to a single firm. Passing tenant_id is now required for every
    production call — the default exists only for safety.
    """
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    sql = text(
        f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM {table_name}
        WHERE embedding IS NOT NULL
          AND tenant_id = :tenant_id
        ORDER BY distance
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"tenant_id": tenant_id, "limit": limit}).fetchall()
    return rows


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------


@router.get("/candidates", response_model=List[CandidateSearchResult])
def search_candidates(
    q: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or RYZE_TENANT  # EP16

    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, "candidates", query_vector, limit, tenant_id)  # EP16
    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    candidates = (
        db.query(Candidate)
        .filter(
            Candidate.id.in_(ids), Candidate.tenant_id == tenant_id
        )  # EP16: double-check
        .all()
    )
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
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or RYZE_TENANT  # EP16

    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(
        db, "employer_profiles", query_vector, limit, tenant_id
    )  # EP16
    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    employers = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.id.in_(ids), EmployerProfile.tenant_id == tenant_id
        )  # EP16
        .all()
    )
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
    current_user: User = Depends(require_admin),
):
    tenant_id = current_user.tenant_id or RYZE_TENANT  # EP16

    query_vector = generate_embedding(q)
    if not query_vector:
        raise HTTPException(status_code=503, detail="Embedding service unavailable.")

    rows = _cosine_search(db, "job_orders", query_vector, limit, tenant_id)  # EP16
    if not rows:
        return []

    ids = [row[0] for row in rows]
    distances = {row[0]: row[1] for row in rows}

    jobs = (
        db.query(JobOrder)
        .filter(JobOrder.id.in_(ids), JobOrder.tenant_id == tenant_id)  # EP16
        .all()
    )
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


def _run_sync_and_log():
    try:
        result = sync_embeddings()  # ← no db argument needed
        logger.info(f"Embedding sync complete: {result}")
    except Exception as e:
        logger.error(f"Embedding sync failed: {e}")
