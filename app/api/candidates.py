# app/api/candidates.py
import io
import logging
from datetime import datetime
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from app.core.database import get_db
from app.models.candidate import Candidate, RYZE_TENANT
from app.api.bookings import require_admin
from app.core.deps import get_current_user
from app.models.user import User, UserType
from app.models.job_order import JobOrder
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


# ---------------------------------------------------------------------------
# Inline response schemas for EP15 matching endpoints
# ---------------------------------------------------------------------------


class CandidateMeResponse(BaseModel):
    id: int
    name: str
    current_title: Optional[str] = None
    ai_career_level: Optional[str] = None
    ai_certifications: Optional[str] = None
    ai_years_experience: Optional[int] = None
    has_embedding: bool

    class Config:
        from_attributes = True


class JobMatchResult(BaseModel):
    id: int
    title: str
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    requirements: Optional[str] = None
    status: str
    employer_profile_id: Optional[int] = None
    match_score: Optional[float] = None  # None = no embedding available

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers — file text extraction
# ---------------------------------------------------------------------------


def _extract_text_from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_text_from_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


# ---------------------------------------------------------------------------
# EP15 — Candidate self-service endpoints (no admin required)
# IMPORTANT: /me and /me/job-matches must be defined BEFORE /{candidate_id}
# so FastAPI does not treat "me" as an integer path param.
# ---------------------------------------------------------------------------


@router.get("/me", response_model=CandidateMeResponse)
def get_my_candidate_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the candidate profile linked to the current user's email.
    Available to candidate users (and admins for testing).
    """
    if not (current_user.user_type == UserType.CANDIDATE or current_user.is_superuser):
        raise HTTPException(
            status_code=403,
            detail="Candidate access required.",
        )

    candidate = (
        db.query(Candidate)
        .filter(Candidate.email == current_user.email)
        .first()
    )
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="No candidate profile found for this account.",
        )

    return CandidateMeResponse(
        id=candidate.id,
        name=candidate.name,
        current_title=candidate.current_title,
        ai_career_level=candidate.ai_career_level,
        ai_certifications=candidate.ai_certifications,
        ai_years_experience=candidate.ai_years_experience,
        has_embedding=candidate.embedding is not None,
    )


@router.get("/me/job-matches", response_model=List[JobMatchResult])
def get_my_job_matches(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    EP15 — Returns open job orders ranked by AI match score for the current candidate.

    Uses the candidate's pgvector embedding as the query vector against
    the job_orders table. Returns results sorted best-match-first.

    Graceful fallback: if the candidate has no embedding yet (e.g. profile
    was just created), returns unranked open job orders with match_score=null.
    """
    if not (current_user.user_type == UserType.CANDIDATE or current_user.is_superuser):
        raise HTTPException(
            status_code=403,
            detail="Candidate access required.",
        )

    candidate = (
        db.query(Candidate)
        .filter(Candidate.email == current_user.email)
        .first()
    )
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="No candidate profile found for this account.",
        )

    def _unranked_fallback() -> List[JobMatchResult]:
        jobs = (
            db.query(JobOrder)
            .filter(JobOrder.status == "open")
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

    # No embedding yet — return unranked
    if candidate.embedding is None:
        logger.info(
            f"Candidate #{candidate.id} ({candidate.name}) has no embedding — "
            "returning unranked job matches."
        )
        return _unranked_fallback()

    # Run cosine similarity: candidate embedding vs open job_orders
    try:
        vector_str = "[" + ",".join(str(v) for v in candidate.embedding) + "]"
        sql = text(
            f"""
            SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
            FROM job_orders
            WHERE embedding IS NOT NULL
              AND status = 'open'
            ORDER BY distance
            LIMIT :limit
            """
        )
        rows = db.execute(sql, {"limit": limit}).fetchall()
    except Exception as e:
        logger.error(f"Cosine search failed for candidate #{candidate.id}: {e}")
        return _unranked_fallback()

    if not rows:
        # No job orders have embeddings yet — unranked fallback
        return _unranked_fallback()

    ids = [r[0] for r in rows]
    distances = {r[0]: float(r[1]) for r in rows}

    jobs = db.query(JobOrder).filter(JobOrder.id.in_(ids)).all()
    job_map = {j.id: j for j in jobs}

    ranked = [
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

    logger.info(
        f"Candidate #{candidate.id} job matches: {len(ranked)} ranked results "
        f"(top score: {ranked[0].match_score if ranked else 'n/a'})"
    )
    return ranked


# ---------------------------------------------------------------------------
# List / get (admin only)
# ---------------------------------------------------------------------------


@router.get("", response_model=List[CandidateResponse])
def list_candidates(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(Candidate).filter(Candidate.tenant_id == RYZE_TENANT)
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
    _: User = Depends(require_admin),
):
    """
    Check for existing candidates with a similar name.
    Optionally narrows by location if provided.
    Returns a list of potential matches — empty list means no duplicates found.
    """
    if not name or len(name.strip()) < 2:
        return []

    tokens = name.strip().lower().split()

    query = db.query(Candidate).filter(Candidate.tenant_id == RYZE_TENANT)
    for token in tokens:
        query = query.filter(Candidate.name.ilike(f"%{token}%"))

    matches = query.order_by(Candidate.created_at.desc()).all()
    return matches


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == RYZE_TENANT)
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
    _: User = Depends(require_admin),
):
    candidate = Candidate(tenant_id=RYZE_TENANT, **payload.model_dump())
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    logger.info(f"Candidate created: {candidate.name} (#{candidate.id})")
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
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == RYZE_TENANT)
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
    _: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == RYZE_TENANT)
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

    try:
        raw_text = (
            _extract_text_from_pdf(data) if is_pdf else _extract_text_from_docx(data)
        )
    except Exception as e:
        logger.error(f"File extraction failed: {e}")
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from this file. Please try a different format.",
        )

    if len(raw_text.strip()) < 50:
        raise HTTPException(
            status_code=422,
            detail="Not enough text found in the file. Please check the file and try again.",
        )

    result = parse_candidate_profile(raw_text)
    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the file. Please try again.",
        )
    return result
