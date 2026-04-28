# app/api/candidates.py
# EP16: Replaced all hardcoded RYZE_TENANT references with dynamic tenant_id
#        extracted from the authenticated admin user.
# EP18: Added email-based duplicate check on create_candidate. When a resume or
#        LinkedIn profile is submitted for an email that already exists in this
#        tenant, the existing record is UPDATED rather than a duplicate created.
#        This covers Scenario A (booking stub + resume upload) and Scenario D
#        (manual create after booking) from the EP18 spec.

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
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import io
from weasyprint import HTML as WeasyHTML
from app.services.spaces import upload_file, make_unique_filename

from app.core.database import get_db
from app.core.deps import get_current_admin_user, RYZE_TENANT
from app.api.auth import get_current_user as get_any_authenticated_user
from app.models.user import User
from app.models.candidate import Candidate
from app.models.job_order import JobOrder
from app.schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateResponse,
    CandidateParseRequest,
    CandidateParseResponse,
    CandidateSelfUpdate,
)
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
# Helper — email duplicate check
# ---------------------------------------------------------------------------


def _find_by_email(db: Session, email: str, tenant_id: str) -> Optional[Candidate]:
    """
    Return an existing candidate with this email in the given tenant, or None.
    Email comparison is case-insensitive.
    """
    if not email or not email.strip():
        return None
    return (
        db.query(Candidate)
        .filter(
            Candidate.email.ilike(email.strip()),
            Candidate.tenant_id == tenant_id,
        )
        .first()
    )


def _resolve_candidate_for_user(db: Session, current_user: User) -> Optional[Candidate]:
    """
    Find the candidate record that belongs to this authenticated user.

    Strategy:
      1. Fast path  — look up by user_id FK (set after first login).
      2. Email fall — match on email within the user's tenant (handles stubs
                      created from bookings before the candidate had an account).
      3. Self-heal  — if the email path finds a record, write user_id onto it
                      so all future lookups use the fast path.

    Returns None if no candidate profile exists yet.
    """
    tenant_id = current_user.tenant_id or RYZE_TENANT

    # 1. Fast path
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if candidate:
        return candidate

    # 2. Email fallback
    if current_user.email:
        candidate = (
            db.query(Candidate)
            .filter(
                Candidate.email.ilike(current_user.email.strip()),
                Candidate.tenant_id == tenant_id,
            )
            .first()
        )
        if candidate:
            # 3. Self-heal: write user_id so future calls are instant
            candidate.user_id = current_user.id
            db.commit()
            db.refresh(candidate)
            logger.info(
                f"[candidates/me] Self-healed: linked user #{current_user.id} "
                f"({current_user.email}) → candidate #{candidate.id}"
            )

    return candidate


@router.get("/me", response_model=CandidateResponse)
def get_my_candidate_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Returns the candidate profile for the currently authenticated user.

    Available to CANDIDATE users. Looks up by user_id (fast path) then
    falls back to email match and self-heals by writing user_id.

    Returns 404 if no profile exists yet — dashboard renders a
    "no profile" state and prompts the candidate to schedule a call.
    """
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="No candidate profile found. Schedule a call with RYZE to get started.",
        )
    return candidate


@router.get("/me/job-matches", response_model=List[JobMatchResult])
def get_my_job_matches(
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Returns open job orders ranked by AI fit for the authenticated candidate.

    Uses the same pgvector cosine similarity logic as the admin-facing
    /{candidate_id}/job-matches endpoint. Falls back to unranked if the
    candidate hasn't been embedded yet.
    """
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")

    tenant_id = current_user.tenant_id or RYZE_TENANT

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

        if not rows:
            return _unranked_fallback()

        ranked_ids = [r.id for r in rows]
        distance_map = {r.id: r.distance for r in rows}

        jobs = db.query(JobOrder).filter(JobOrder.id.in_(ranked_ids)).all()
        job_map = {j.id: j for j in jobs}

        return [
            JobMatchResult(
                id=job_map[jid].id,
                title=job_map[jid].title,
                location=job_map[jid].location,
                salary_min=job_map[jid].salary_min,
                salary_max=job_map[jid].salary_max,
                requirements=job_map[jid].requirements,
                status=job_map[jid].status,
                employer_profile_id=job_map[jid].employer_profile_id,
                match_score=round(1 - distance_map[jid], 4),
            )
            for jid in ranked_ids
            if jid in job_map
        ]

    except Exception as e:
        logger.error(f"[candidates/me/job-matches] Vector search failed: {e}")
        return _unranked_fallback()


@router.patch("/me", response_model=CandidateResponse)
def update_my_candidate_profile(
    payload: CandidateSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    """
    Allows a candidate to update their own basic profile fields.
    Recruiter-owned fields (AI summary, notes, skills, etc.) are not exposed
    here — they can only be updated by an admin.
    """
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(candidate, field, value)

    candidate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(candidate)

    logger.info(
        f"[candidates/me PATCH] Candidate #{candidate.id} updated fields: "
        f"{list(update_data.keys())} by user #{current_user.id}"
    )
    return candidate


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
    current_user: User = Depends(require_admin),
):
    tenant_id = _tenant(current_user)

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
    current_user: User = Depends(require_admin),
):
    """
    Check for existing candidates with a similar name within this tenant.
    Returns a list of potential matches — empty list means no duplicates found.
    """
    tenant_id = _tenant(current_user)

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
    return candidate


# ---------------------------------------------------------------------------
# Create (admin only)
# EP18: Email-based upsert — if a candidate with the same email already exists
# in this tenant, update the existing record instead of creating a duplicate.
# This silently merges rather than rejecting, which is the correct behaviour
# for the resume-upload-after-booking-stub scenario (Scenario A in the spec).
# ---------------------------------------------------------------------------


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tenant_id = _tenant(current_user)
    data = payload.model_dump()
    incoming_email = data.get("email")

    # ── EP18: Email duplicate check ──────────────────────────────────────
    # If a candidate with this email already exists in the tenant, update
    # that record rather than creating a second one. Preserves booking_id,
    # source, meeting_transcript, and any other fields already on the stub.
    existing = _find_by_email(db, incoming_email, tenant_id)

    if existing:
        logger.info(
            f"[EP18] create_candidate: email '{incoming_email}' matches existing "
            f"candidate #{existing.id} ({existing.name}) — merging instead of creating duplicate"
        )

        # Merge: only overwrite fields that are non-null in the incoming payload
        # and not already set on the existing record. This way a booking stub's
        # name/email/phone are preserved if resume parse returns the same data,
        # and richer fields (title, company, AI fields) fill in the blanks.
        PRESERVE_IF_SET = {"booking_id", "source", "meeting_transcript", "tenant_id"}

        for field, value in data.items():
            if field in PRESERVE_IF_SET:
                # Never overwrite these — they belong to the stub's origin
                continue
            if value is not None:
                setattr(existing, field, value)

        # If the existing record was a stub (source='booking') and the incoming
        # payload came from a resume or LinkedIn parse, upgrade the source label
        # so it reflects the enrichment that just happened.
        if existing.source == "booking" and data.get("source") in (
            "resume",
            "linkedin",
            None,
        ):
            # Keep 'booking' as the origin — enrichment doesn't erase the history.
            # The frontend shows "Created from Call" which remains accurate.
            pass

        existing.embedding = None
        existing.embedded_at = None
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        background_tasks.add_task(embed_candidate_background, existing.id)

        logger.info(
            f"[EP18] Merged & re-embedded candidate #{existing.id} ({existing.name})"
        )
        return existing

    # ── Normal create path (no duplicate found) ──────────────────────────
    candidate = Candidate(tenant_id=tenant_id, **data)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    logger.info(
        f"Candidate created: {candidate.name} (#{candidate.id}) tenant={tenant_id}"
    )
    background_tasks.add_task(embed_candidate_background, candidate.id)
    return candidate


# ---------------------------------------------------------------------------
# Update / delete (admin only)
# ---------------------------------------------------------------------------


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    background_tasks: BackgroundTasks,
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


# ---------------------------------------------------------------------------
# Single embed
# ---------------------------------------------------------------------------


@router.post("/{candidate_id}/embed")
def embed_single_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(
            Candidate.id == candidate_id,
            Candidate.tenant_id == _tenant(current_user),
        )
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    text = build_candidate_text(candidate)
    if not text:
        raise HTTPException(
            status_code=400, detail="Not enough data to embed this candidate"
        )

    vector = generate_embedding(text)
    if not vector:
        raise HTTPException(status_code=500, detail="Embedding generation failed")

    candidate.embedding = vector
    candidate.embedded_at = datetime.utcnow()
    db.commit()

    return {"id": candidate_id, "embedded_at": candidate.embedded_at.isoformat()}


# ---------------------------------------------------------------------------
# Embed all unindexed
# ---------------------------------------------------------------------------


@router.post("/embed-all")
def embed_all_candidates(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    unembedded = (
        db.query(Candidate)
        .filter(
            Candidate.tenant_id == _tenant(current_user),
            Candidate.embedding.is_(None),
        )
        .all()
    )
    count = len(unembedded)
    for c in unembedded:
        background_tasks.add_task(embed_candidate_background, c.id)

    return {"queued": count, "message": f"{count} candidate(s) queued for indexing"}


@router.post("/{candidate_id}/photo")
async def upload_candidate_photo(
    candidate_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a headshot for a candidate.
    Stores the image in DO Spaces and saves the CDN URL to photo_url.
    """
    tenant_id = _tenant(current_user)
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Validate image type
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a JPEG, PNG, or WebP image.",
        )

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400, detail="Image too large. Maximum size is 5MB."
        )

    unique_name = make_unique_filename(file.filename or "photo.jpg")
    folder = f"candidates/{candidate_id}/photo"

    cdn_url = upload_file(data, folder, unique_name, file.content_type)
    if not cdn_url:
        raise HTTPException(
            status_code=500, detail="Photo upload failed. Please try again."
        )

    candidate.photo_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"[EP18] Photo uploaded for candidate #{candidate_id}: {cdn_url}")
    return {"photo_url": cdn_url}


# ─────────────────────────────────────────────────────────────────────────────
# BANNER UPLOAD  —  POST /api/candidates/{candidate_id}/banner
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{candidate_id}/banner")
async def upload_candidate_banner(
    candidate_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a banner/cover image for a candidate (like LinkedIn).
    Stores in DO Spaces and saves the CDN URL to banner_url.
    """
    tenant_id = _tenant(current_user)
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a JPEG, PNG, or WebP image.",
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400, detail="Image too large. Maximum size is 10MB."
        )

    unique_name = make_unique_filename(file.filename or "banner.jpg")
    folder = f"candidates/{candidate_id}/banner"

    cdn_url = upload_file(data, folder, unique_name, file.content_type)
    if not cdn_url:
        raise HTTPException(
            status_code=500, detail="Banner upload failed. Please try again."
        )

    candidate.banner_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"[EP18] Banner uploaded for candidate #{candidate_id}: {cdn_url}")
    return {"banner_url": cdn_url}


# ─────────────────────────────────────────────────────────────────────────────
# PDF EXPORT  —  GET /api/candidates/{candidate_id}/pdf
# ─────────────────────────────────────────────────────────────────────────────

PDF_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap');
 
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
 
  body {{
    font-family: 'DM Sans', Arial, sans-serif;
    font-size: 11px;
    color: #1e293b;
    background: #fff;
    padding: 0;
  }}
 
  /* ── Banner ── */
  .banner {{
    width: 100%;
    height: 110px;
    background: {banner_style};
    background-size: cover;
    background-position: center;
  }}
 
  /* ── Header ── */
  .header {{
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px 36px 20px;
    border-bottom: 2px solid #e2e8f0;
    margin-top: -36px;
  }}
 
  .photo-wrap {{
    flex-shrink: 0;
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: 3px solid #fff;
    overflow: hidden;
    background: #1e3a5f;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    margin-top: 0;
  }}
 
  .photo-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
 
  .photo-initial {{
    font-size: 28px;
    font-weight: 700;
    color: #fff;
  }}
 
  .header-info {{
    flex: 1;
    padding-top: 38px;
  }}
 
  .candidate-name {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 22px;
    font-weight: 400;
    color: #0f172a;
    line-height: 1.2;
    margin-bottom: 4px;
  }}
 
  .candidate-meta {{
    font-size: 11px;
    color: #475569;
    margin-bottom: 3px;
  }}
 
  .candidate-location {{
    font-size: 10px;
    color: #64748b;
  }}
 
  .badges {{
    display: flex;
    gap: 6px;
    margin-top: 6px;
    flex-wrap: wrap;
  }}
 
  .badge {{
    font-size: 9px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    border: 1px solid;
    text-transform: capitalize;
  }}
 
  .badge-level {{
    background: #eff6ff;
    color: #1d4ed8;
    border-color: #bfdbfe;
  }}
 
  .badge-cert {{
    background: #1d4ed8;
    color: #fff;
    border-color: #1d4ed8;
  }}
 
  .badge-exp {{
    background: #f1f5f9;
    color: #475569;
    border-color: #cbd5e1;
  }}
 
  /* ── Body ── */
  .body {{
    padding: 20px 36px;
    display: flex;
    gap: 24px;
  }}
 
  .main-col {{
    flex: 1;
    min-width: 0;
  }}
 
  .side-col {{
    width: 180px;
    flex-shrink: 0;
  }}
 
  /* ── Sections ── */
  .section {{
    margin-bottom: 18px;
  }}
 
  .section-title {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #94a3b8;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-bottom: 8px;
  }}
 
  .section-text {{
    font-size: 10.5px;
    color: #334155;
    line-height: 1.7;
  }}
 
  /* ── Skills ── */
  .skills-wrap {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }}
 
  .skill-tag {{
    font-size: 9px;
    font-weight: 600;
    padding: 2px 8px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    border-radius: 999px;
  }}
 
  /* ── Contact rows ── */
  .info-row {{
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    margin-bottom: 5px;
    gap: 8px;
  }}
 
  .info-label {{
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    font-size: 8.5px;
    letter-spacing: 0.05em;
    flex-shrink: 0;
  }}
 
  .info-value {{
    color: #334155;
    text-align: right;
    word-break: break-all;
  }}
 
  /* ── Footer ── */
  .footer {{
    margin-top: 8px;
    padding: 10px 36px;
    border-top: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
 
  .footer-brand {{
    font-size: 9px;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }}
 
  .footer-note {{
    font-size: 8.5px;
    color: #cbd5e1;
  }}
</style>
</head>
<body>
 
  <!-- Banner -->
  <div class="banner"></div>
 
  <!-- Header -->
  <div class="header">
    <div class="photo-wrap">
      {photo_tag}
    </div>
    <div class="header-info">
      <div class="candidate-name">{name}</div>
      {meta_line}
      {location_line}
      <div class="badges">
        {badges}
      </div>
    </div>
  </div>
 
  <!-- Body -->
  <div class="body">
    <div class="main-col">
      {summary_section}
      {experience_section}
      {education_section}
    </div>
    <div class="side-col">
      {contact_section}
      {skills_section}
      {certs_section}
    </div>
  </div>
 
  <!-- Footer -->
  <div class="footer">
    <span class="footer-brand">RYZE.ai</span>
    <span class="footer-note">Prepared by your RYZE recruiter</span>
  </div>
 
</body>
</html>
"""


def _section(title: str, content: str) -> str:
    return (
        f'<div class="section"><div class="section-title">{title}</div>{content}</div>'
    )


def _info_row(label: str, value: str) -> str:
    return f'<div class="info-row"><span class="info-label">{label}</span><span class="info-value">{value}</span></div>'


@router.get("/{candidate_id}/pdf")
def download_candidate_pdf(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate and stream a branded PDF profile for a candidate.
    Uses WeasyPrint to render the HTML template to PDF.
    """
    from fastapi.responses import StreamingResponse
    import io
    from weasyprint import HTML as WeasyHTML

    tenant_id = _tenant(current_user)
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # ── Banner style ──────────────────────────────────────────────────────
    if candidate.banner_url:
        banner_style = f"linear-gradient(rgba(0,26,51,0.35), rgba(0,26,51,0.35)), url('{candidate.banner_url}')"
    else:
        banner_style = "linear-gradient(135deg, #001a33 0%, #0a3a5c 60%, #1d4ed8 100%)"

    # ── Photo tag ─────────────────────────────────────────────────────────
    if candidate.photo_url:
        photo_tag = f'<img src="{candidate.photo_url}" alt="{candidate.name}" />'
    else:
        initial = candidate.name[0].upper() if candidate.name else "?"
        photo_tag = f'<span class="photo-initial">{initial}</span>'

    # ── Meta line ─────────────────────────────────────────────────────────
    meta_parts = [p for p in [candidate.current_title, candidate.current_company] if p]
    meta_line = (
        f'<div class="candidate-meta">{" · ".join(meta_parts)}</div>'
        if meta_parts
        else ""
    )

    location_line = (
        f'<div class="candidate-location">📍 {candidate.location}</div>'
        if candidate.location
        else ""
    )

    # ── Badges ────────────────────────────────────────────────────────────
    badges = ""
    if candidate.ai_career_level:
        badges += f'<span class="badge badge-level">{candidate.ai_career_level}</span>'
    if candidate.ai_years_experience:
        badges += f'<span class="badge badge-exp">{candidate.ai_years_experience} yrs exp</span>'
    certs_text = candidate.ai_certifications or ""
    for cert in ["CPA", "CFA", "CMA"]:
        if cert in certs_text:
            badges += f'<span class="badge badge-cert">{cert}</span>'

    # ── Main sections ─────────────────────────────────────────────────────
    summary_section = ""
    if candidate.ai_summary:
        summary_section = _section(
            "Professional Summary",
            f'<p class="section-text">{candidate.ai_summary}</p>',
        )

    experience_section = ""
    if candidate.ai_experience:
        experience_section = _section(
            "Experience", f'<p class="section-text">{candidate.ai_experience}</p>'
        )

    education_section = ""
    if candidate.ai_education:
        education_section = _section(
            "Education", f'<p class="section-text">{candidate.ai_education}</p>'
        )

    # ── Sidebar sections ──────────────────────────────────────────────────
    contact_rows = ""
    if candidate.email:
        contact_rows += _info_row("Email", candidate.email)
    if candidate.phone:
        contact_rows += _info_row("Phone", candidate.phone)
    if candidate.linkedin_url:
        contact_rows += _info_row("LinkedIn", "linkedin.com/in/…")
    contact_section = _section("Contact", contact_rows) if contact_rows else ""

    skills_section = ""
    if candidate.ai_skills:
        tags = "".join(
            f'<span class="skill-tag">{s}</span>' for s in (candidate.ai_skills or [])
        )
        skills_section = _section("Skills", f'<div class="skills-wrap">{tags}</div>')

    certs_section = ""
    if candidate.ai_certifications:
        certs_section = _section(
            "Certifications",
            f'<p class="section-text">{candidate.ai_certifications}</p>',
        )

    # ── Render ────────────────────────────────────────────────────────────
    html = PDF_TEMPLATE.format(
        banner_style=banner_style,
        photo_tag=photo_tag,
        name=candidate.name,
        meta_line=meta_line,
        location_line=location_line,
        badges=badges,
        summary_section=summary_section,
        experience_section=experience_section,
        education_section=education_section,
        contact_section=contact_section,
        skills_section=skills_section,
        certs_section=certs_section,
    )

    try:
        pdf_bytes = WeasyHTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"[EP18] PDF generation failed for candidate #{candidate_id}: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed.")

    safe_name = (candidate.name or "candidate").replace(" ", "_")
    filename = f"{safe_name}_profile.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
