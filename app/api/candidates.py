# app/api/candidates.py
# EP16: Replaced all hardcoded RYZE_TENANT references with dynamic tenant_id
# extracted from the authenticated admin user. Every query, create, and ownership
# check now uses current_user.tenant_id so the same codebase serves any firm.

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_admin_user, RYZE_TENANT
from app.models.user import User
from app.models.candidate import Candidate
from app.models.job_order import JobOrder
from app.schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateResponse,
    CandidateParseRequest,
    CandidateParseResponse,
)
from datetime import datetime
from app.schemas.job_order import JobMatchResult
from app.services.embedding_service import (
    embed_candidate_background,
    build_candidate_text,
    generate_embedding,
)
from app.services.ai_parser import parse_candidate_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

# Convenience alias — keeps existing code readable
require_admin = get_current_admin_user


# ---------------------------------------------------------------------------
# Helper — resolve tenant from current user
# ---------------------------------------------------------------------------


def _tenant(user: User) -> str:
    """Return the user's tenant_id, falling back to 'ryze' for legacy NULLs."""
    return user.tenant_id or RYZE_TENANT


# ---------------------------------------------------------------------------
# Job matching — candidate → ranked open roles (candidate-facing)
# ---------------------------------------------------------------------------


@router.get("/{candidate_id}/job-matches", response_model=List[JobMatchResult])
def get_job_matches(
    candidate_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = _tenant(current_user)

    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    def _unranked_fallback():
        jobs = (
            db.query(JobOrder)
            .filter(JobOrder.status == "open", JobOrder.tenant_id == tenant_id)
            .order_by(JobOrder.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            JobMatchResult(
                id=j.id,
                title=j.title,
                location=j.location,
                salary_min=j.salary_min,
                salary_max=j.salary_max,
                requirements=j.requirements,
                status=j.status,
                employer_profile_id=j.employer_profile_id,
                match_score=None,
            )
            for j in jobs
        ]

    if candidate.embedding is None:
        return _unranked_fallback()

    try:
        vector_str = "[" + ",".join(str(v) for v in candidate.embedding) + "]"
        sql = text(
            f"""
            SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
            FROM job_orders
            WHERE embedding IS NOT NULL
              AND status = 'open'
              AND tenant_id = :tenant_id
            ORDER BY distance
            LIMIT :limit
            """
        )
        rows = db.execute(sql, {"tenant_id": tenant_id, "limit": limit}).fetchall()
    except Exception as e:
        logger.error(f"Cosine search failed for candidate #{candidate_id}: {e}")
        return _unranked_fallback()

    if not rows:
        return _unranked_fallback()

    ids = [r[0] for r in rows]
    distances = {r[0]: float(r[1]) for r in rows}

    jobs = (
        db.query(JobOrder)
        .filter(JobOrder.id.in_(ids), JobOrder.tenant_id == tenant_id)
        .all()
    )
    job_map = {j.id: j for j in jobs}

    return [
        JobMatchResult(
            id=job_map[cid].id,
            title=job_map[cid].title,
            location=job_map[cid].location,
            salary_min=job_map[cid].salary_min,
            salary_max=job_map[cid].salary_max,
            requirements=job_map[cid].requirements,
            status=job_map[cid].status,
            employer_profile_id=job_map[cid].employer_profile_id,
            match_score=round(max(0.0, 1.0 - distances[cid]), 4),
        )
        for cid in ids
        if cid in job_map
    ]


# ---------------------------------------------------------------------------
# List / get (admin only)
# ---------------------------------------------------------------------------


@router.get("", response_model=List[CandidateResponse])
def list_candidates(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    query = db.query(Candidate).filter(Candidate.tenant_id == tenant_id)
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


@router.get("/check-duplicate", response_model=List[CandidateResponse])
def check_duplicate(
    name: str,
    location: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    """
    Check for existing candidates with a similar name within this tenant.
    Returns a list of potential matches — empty list means no duplicates found.
    """
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    if not name or len(name.strip()) < 2:
        return []

    tokens = name.strip().lower().split()
    query = db.query(Candidate).filter(Candidate.tenant_id == tenant_id)
    for token in tokens:
        query = query.filter(Candidate.name.ilike(f"%{token}%"))

    return query.order_by(Candidate.created_at.desc()).all()


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return candidate


# ---------------------------------------------------------------------------
# Create / update / delete (admin only)
# ---------------------------------------------------------------------------


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    candidate = Candidate(tenant_id=tenant_id, **payload.model_dump())
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    logger.info(
        f"Candidate created: {candidate.name} (#{candidate.id}) tenant={tenant_id}"
    )
    background_tasks.add_task(embed_candidate_background, candidate.id)
    return candidate


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(candidate, field, value)

    candidate.embedding = None
    candidate.embedded_at = None
    candidate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(candidate)
    background_tasks.add_task(embed_candidate_background, candidate.id)
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # EP16: was `_`
):
    tenant_id = _tenant(current_user)  # EP16: was RYZE_TENANT

    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    db.delete(candidate)
    db.commit()


# ---------------------------------------------------------------------------
# Parse — text paste (admin only)
# ---------------------------------------------------------------------------


@router.post("/parse", response_model=CandidateParseResponse)
def parse_candidate(
    payload: CandidateParseRequest,
    _: User = Depends(require_admin),
):
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


# ---------------------------------------------------------------------------
# Parse — file upload PDF or DOCX (admin only)
# ---------------------------------------------------------------------------


@router.post("/parse-file", response_model=CandidateParseResponse)
async def parse_candidate_file(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    filename = file.filename or ""
    content_type = file.content_type or ""

    is_pdf = filename.lower().endswith(".pdf") or content_type == "application/pdf"
    is_docx = filename.lower().endswith(".docx") or content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    )

    if not is_pdf and not is_docx:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF or Word (.docx) document.",
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400, detail="File too large. Maximum size is 10MB."
        )

    result = parse_candidate_profile(data, filename=filename, content_type=content_type)
    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the file. Please try again or use text paste.",
        )
    return result


# ── Single embed — line ~358 ──
@router.post("/{candidate_id}/embed")
def embed_single_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # ← was get_current_user
):
    candidate = (
        db.query(Candidate)
        .filter(
            Candidate.id == candidate_id,
            Candidate.tenant_id == _tenant(current_user),  # ← use _tenant()
        )
        .first()
    )
    ...


# ── Embed all — further down ──
@router.post("/embed-all")
def embed_all_candidates(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # ← was get_current_user
):
    unembedded = (
        db.query(Candidate)
        .filter(
            Candidate.tenant_id == _tenant(current_user),  # ← use _tenant()
            Candidate.embedding.is_(None),
        )
        .all()
    )
