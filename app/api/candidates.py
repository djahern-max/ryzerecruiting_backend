# app/api/candidates.py

import logging
from datetime import datetime
from typing import List, Optional
import html
import json
import re

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
from playwright.sync_api import sync_playwright
from app.services.spaces import upload_file, make_unique_filename, delete_file
from app.core.config import settings

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

require_admin = get_current_admin_user


def _tenant(user: User) -> str:
    return user.tenant_id or RYZE_TENANT


def _find_by_email(db: Session, email: str, tenant_id: str) -> Optional[Candidate]:
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
    tenant_id = current_user.tenant_id or RYZE_TENANT

    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if candidate:
        return candidate

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
            candidate.user_id = current_user.id
            db.commit()
            db.refresh(candidate)
    return candidate


@router.get("/me", response_model=CandidateResponse)
def get_my_candidate_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")
    return candidate


@router.get("/me/job-matches", response_model=List[JobMatchResult])
def get_my_job_matches(
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
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
        sql = text(f"""
            SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
            FROM job_orders
            WHERE embedding IS NOT NULL AND status = 'open' AND tenant_id = :tenant_id
            ORDER BY distance LIMIT :limit
            """)
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
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(candidate, field, value)

    candidate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(candidate)
    return candidate


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
        sql = text(f"""
            SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
            FROM job_orders
            WHERE embedding IS NOT NULL AND status = 'open' AND tenant_id = :tenant_id
            ORDER BY distance LIMIT :limit
            """)
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

    existing = _find_by_email(db, incoming_email, tenant_id)
    if existing:
        PRESERVE_IF_SET = {"booking_id", "source", "meeting_transcript", "tenant_id"}
        for field, value in data.items():
            if field in PRESERVE_IF_SET:
                continue
            if value is not None:
                setattr(existing, field, value)
        existing.embedding = None
        existing.embedded_at = None
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        background_tasks.add_task(embed_candidate_background, existing.id)
        return existing

    candidate = Candidate(tenant_id=tenant_id, **data)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    background_tasks.add_task(embed_candidate_background, candidate.id)
    return candidate


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


@router.post("/parse", response_model=CandidateParseResponse)
def parse_candidate(
    payload: CandidateParseRequest,
    _: User = Depends(require_admin),
):
    if not payload.text or len(payload.text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text is too short to parse.")
    result = parse_candidate_profile(payload.text)
    if not result:
        raise HTTPException(
            status_code=422, detail="Could not parse the provided text."
        )
    return result


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
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB).")

    result = parse_candidate_profile(data, filename=filename, content_type=content_type)
    if not result:
        raise HTTPException(status_code=422, detail="Could not parse the file.")
    return result


@router.post("/{candidate_id}/embed")
def embed_single_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    candidate = (
        db.query(Candidate)
        .filter(
            Candidate.id == candidate_id, Candidate.tenant_id == _tenant(current_user)
        )
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    text = build_candidate_text(candidate)
    if not text:
        raise HTTPException(status_code=400, detail="Not enough data to embed")

    vector = generate_embedding(text)
    if not vector:
        raise HTTPException(status_code=500, detail="Embedding generation failed")

    candidate.embedding = vector
    candidate.embedded_at = datetime.utcnow()
    db.commit()
    return {"id": candidate_id, "embedded_at": candidate.embedded_at.isoformat()}


@router.post("/embed-all")
def embed_all_candidates(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    unembedded = (
        db.query(Candidate)
        .filter(
            Candidate.tenant_id == _tenant(current_user), Candidate.embedding.is_(None)
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
    tenant_id = _tenant(current_user)
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB).")

    if candidate.photo_url:
        old_key = candidate.photo_url.replace(
            settings.DO_SPACES_CDN_BASE.rstrip("/") + "/", ""
        )
        delete_file(old_key)

    unique_name = make_unique_filename(file.filename or "photo.jpg")
    cdn_url = upload_file(
        data, f"candidates/{candidate_id}/photo", unique_name, file.content_type
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Photo upload failed.")

    candidate.photo_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()
    return {"photo_url": cdn_url}


@router.post("/{candidate_id}/banner")
async def upload_candidate_banner(
    candidate_id: int,
    file: UploadFile = File(...),
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

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    if candidate.banner_url:
        old_key = candidate.banner_url.replace(
            settings.DO_SPACES_CDN_BASE.rstrip("/") + "/", ""
        )
        delete_file(old_key)

    unique_name = make_unique_filename(file.filename or "banner.jpg")
    cdn_url = upload_file(
        data, f"candidates/{candidate_id}/banner", unique_name, file.content_type
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Banner upload failed.")

    candidate.banner_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()
    return {"banner_url": cdn_url}


# ─────────────────────────────────────────────────────────────────────────────
# PDF EXPORT  (Playwright / headless Chromium)
# CSS mirrors CandidateProfile.module.css as closely as possible.
# ─────────────────────────────────────────────────────────────────────────────

_PDF_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=DM+Serif+Display&display=swap');

@page {{
    margin: 0;
    size: 8.5in 11in;
}}

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

body {{
    font-family: 'DM Sans', Arial, Helvetica, sans-serif;
    font-size: 10px;
    color: #1e293b;
    background: #f1f5f9;
    width: 8.5in;
    display: flex;
    flex-direction: column;
    min-height: 11in;
}}

/* ─── HERO — mirrors .heroBanner ─── */
.hero {{
    position: relative;
    width: 100%;
    height: 260px;
    background: {banner_style};
    background-size: cover;
    background-position: center;
    overflow: hidden;
    flex-shrink: 0;
    display: flex;
    align-items: center;
}}

/* mirrors .heroScrim */
.hero-scrim {{
    position: absolute;
    inset: 0;
    background: linear-gradient(
        to bottom,
        transparent 0%,
        rgba(8, 18, 38, 0.25) 40%,
        rgba(8, 18, 38, 0.65) 70%,
        rgba(8, 18, 38, 0.78) 100%
    );
    z-index: 1;
}}

/* mirrors .identityOverlay */
.hero-identity {{
    position: relative;
    z-index: 2;
    width: 100%;
    padding: 0 40px;
    display: flex;
    align-items: center;
    gap: 22px;
}}

/* mirrors .avatarWrap / .avatarImg / .avatarInitial */
.avatar {{
    width: 88px;
    height: 88px;
    border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, 0.4);
    background: rgba(255, 255, 255, 0.12);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}

.avatar img {{
    width: 88px;
    height: 88px;
    object-fit: cover;
    display: block;
    border-radius: 50%;
}}

.avatar-initial {{
    font-size: 2.2rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
    line-height: 1;
}}

/* mirrors .headerInfo */
.identity-info {{
    flex: 1;
    min-width: 0;
}}

/* mirrors .candidateName */
.candidate-name {{
    font-size: 28px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.5px;
    line-height: 1.1;
    text-shadow: 0 1px 10px rgba(0, 0, 0, 0.45);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* mirrors .candidateMeta */
.candidate-meta {{
    font-size: 11px;
    color: rgba(255, 255, 255, 0.85);
    font-weight: 500;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}}

.meta-divider {{
    color: rgba(255, 255, 255, 0.38);
    font-style: italic;
    font-size: 10px;
}}

/* mirrors .candidateLocation */
.candidate-location {{
    font-size: 9px;
    color: rgba(255, 255, 255, 0.55);
    margin-bottom: 8px;
    letter-spacing: 0.01em;
}}

.badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}}

.badge {{
    font-size: 9px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 20px;
    border: 1px solid;
    letter-spacing: 0.04em;
    text-transform: capitalize;
    white-space: nowrap;
}}

/* mirrors CAREER_LEVEL_COLORS */
.badge-exec  {{ background: #0f172a;  color: #f8fafc; border-color: #1e293b; }}
.badge-level {{ background: #eff6ff;  color: #1d4ed8; border-color: #bfdbfe; }}
.badge-exp   {{ background: rgba(255,255,255,0.18); color: #ffffff; border-color: rgba(255,255,255,0.32); }}
.badge-cert  {{ background: #1d4ed8;  color: #ffffff; border-color: #3b82f6; }}

/* ─── ACCENT BAR ─── */
.accent-bar {{
    width: 100%;
    height: 3px;
    background: linear-gradient(to right, #1e3a5f, #2563eb, #1e3a5f);
    flex-shrink: 0;
}}

/* ─── BODY — mirrors .profileBody / .profileBodyInner ─── */
.body {{
    flex: 1;
    display: flex;
    gap: 20px;
    padding: 22px 28px;
    align-items: flex-start;
    background: #f1f5f9;
}}

.main-col {{
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
}}

.side-col {{
    width: 255px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
}}

/* ─── SECTION CARD — mirrors .section + .sectionTitle + .sectionBody ─── */
.card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    overflow: hidden;
    page-break-inside: avoid;
}}

.card-title {{
    font-size: 8px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #94a3b8;
    padding: 11px 16px 10px;
    border-bottom: 1px solid #f1f5f9;
    background: #f8fafc;
}}

.card-body {{
    padding: 14px 16px;
}}

/* mirrors .summaryText */
.summary-text {{
    font-size: 10px;
    color: #334155;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
}}

/* mirrors .bodyText */
.body-text {{
    font-size: 9.5px;
    color: #334155;
    line-height: 1.75;
    white-space: pre-wrap;
    word-break: break-word;
}}

/* ─── SKILLS — mirrors .skillTag ─── */
.skills-wrap {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}}

.skill-tag {{
    font-size: 9px;
    font-weight: 500;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    color: #334155;
    border-radius: 6px;
    padding: 3px 8px;
}}

/* ─── CERT BADGES — mirrors .certBadge ─── */
.cert-badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
}}

.cert-badge {{
    font-size: 9px;
    font-weight: 700;
    border-radius: 20px;
    background: #1d4ed8;
    border: 1px solid #3b82f6;
    color: #ffffff;
    padding: 3px 10px;
}}

/* ─── INFO ROWS — mirrors .infoRow / .infoLabel / .infoValue ─── */
.info-list {{
    display: flex;
    flex-direction: column;
    gap: 9px;
}}

.info-row {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
}}

.info-label {{
    font-size: 8px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #94a3b8;
    flex-shrink: 0;
    width: 66px;
    padding-top: 1px;
}}

.info-value {{
    font-size: 9.5px;
    color: #1e293b;
    word-break: break-word;
    line-height: 1.35;
}}

.bullet-list {{
    margin: 0;
    padding: 0 0 0 16px;
    display: flex;
    flex-direction: column;
    gap: 7px;
}}

.bullet-list li {{
    font-size: 9.5px;
    color: #334155;
    line-height: 1.55;
    padding-left: 4px;
}}

/* ─── FOOTER ─── */
.footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 2px solid #1e3a5f;
    background: #0f2444;
    padding: 9px 36px;
    flex-shrink: 0;
}}

.footer-left {{
    display: flex;
    align-items: center;
}}

.footer-brand {{
    font-size: 9px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.2em;
    text-transform: uppercase;
}}

.footer-sep {{
    display: inline-block;
    width: 1px;
    height: 10px;
    background: rgba(255, 255, 255, 0.3);
    margin: 0 10px;
}}

.footer-tagline {{
    font-size: 8px;
    color: rgba(255, 255, 255, 0.55);
}}

.footer-date {{
    font-size: 8px;
    color: rgba(255, 255, 255, 0.55);
}}
"""

_PDF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>{style}</style>
</head>
<body>

<!-- HERO -->
<div class="hero">
  <div class="hero-scrim"></div>
  <div class="hero-identity">
    <div class="avatar">{photo_tag}</div>
    <div class="identity-info">
      <div class="candidate-name">{name}</div>
      {meta_line}
      {location_line}
      <div class="badges">{badges}</div>
    </div>
  </div>
</div>

<!-- ACCENT BAR -->
<div class="accent-bar"></div>

<!-- BODY -->
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
    {details_section}
  </div>

</div>

<!-- FOOTER -->
<div class="footer">
  <div class="footer-left">
    <span class="footer-brand">RYZE.ai</span>
    <span class="footer-sep"></span>
    <span class="footer-tagline">Prepared by your RYZE recruiter</span>
  </div>
  <div class="footer-date">Generated {today}</div>
</div>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _render_pdf(html_string: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_string, wait_until="networkidle")
        pdf = page.pdf(
            format="Letter",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    return pdf


def _card(title: str, inner: str) -> str:
    """Mirrors .section > .sectionTitle + .sectionBody"""
    if not inner.strip():
        return ""
    return (
        f'<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-body">{inner}</div>'
        f"</div>"
    )


def _info_row(label: str, value: str) -> str:
    return (
        f'<div class="info-row">'
        f'<span class="info-label">{label}</span>'
        f'<span class="info-value">{value}</span>'
        f"</div>"
    )


def _badge(cls: str, text: str) -> str:
    return f'<span class="badge {cls}">{text}</span>'


def _e(value) -> str:
    return html.escape(str(value or ""))


def _clean_text(value, max_chars=900) -> str:
    t = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(t) <= max_chars:
        return _e(t)
    return _e(t[:max_chars].rstrip() + "…")


def _parse_skills(value):
    if not value:
        return []
    if isinstance(value, list):
        return value[:14]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed[:14]
        except Exception:
            return [s.strip() for s in value.split(",") if s.strip()][:14]
    return []


def _parse_to_bullets(text: str, max_items: int = 6) -> str:
    """
    Converts prose experience/education text into HTML bullet points.
    Strips redundant subject pronouns from the start of each sentence.
    """
    if not text:
        return ""
    raw = str(text).strip()

    # Split on sentence boundaries
    sentences = re.split(r"(?<=\.)\s+(?=[A-Z])", raw)

    # Prefixes to strip from bullet starts
    STRIP_PREFIXES = (
        "He then ",
        "He also ",
        "He currently ",
        "He is currently ",
        "She then ",
        "She also ",
        "She currently ",
        "She is currently ",
        "They then ",
        "They also ",
        "They currently ",
        "He ",
        "She ",
        "They ",
        "Concurrently, he ",
        "Concurrently, she ",
        "Concurrently, they ",
    )

    bullets = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        # Skip generic opening sentence ("Dane Ahern has an extensive career...")
        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+ has (an|a) ", s):
            continue
        # Strip subject pronouns and recapitalize
        for prefix in STRIP_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix) :]
                s = s[0].upper() + s[1:]
                break
        bullets.append(s)

    bullets = bullets[:max_items]
    if not bullets:
        return f'<p class="body-text">{_e(raw)}</p>'
    items = "".join(f"<li>{_e(b)}</li>" for b in bullets)
    return f'<ul class="bullet-list">{items}</ul>'


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{candidate_id}/pdf")
def download_candidate_pdf(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Stream a branded PDF profile for a candidate via headless Chromium."""
    tenant_id = _tenant(current_user)
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    today_str = datetime.utcnow().strftime("%B %d, %Y")

    # ── Banner ────────────────────────────────────────────────────────────
    if candidate.banner_url:
        banner_style = f"url('{candidate.banner_url}')"
    else:
        banner_style = "linear-gradient(135deg, #0f2444 0%, #1a3a6b 60%, #1e4a8a 100%)"

    # ── Avatar ────────────────────────────────────────────────────────────
    if candidate.photo_url:
        photo_tag = f'<img src="{candidate.photo_url}" alt="" />'
    else:
        initial = (candidate.name or "?")[0].upper()
        photo_tag = f'<span class="avatar-initial">{initial}</span>'

    # ── Name / meta — mirrors .candidateMeta with metaDivider ────────────
    title_part = _e(candidate.current_title) if candidate.current_title else ""
    company_part = _e(candidate.current_company) if candidate.current_company else ""
    if title_part and company_part:
        meta_line = (
            f'<div class="candidate-meta">'
            f"<span>{title_part}</span>"
            f'<span class="meta-divider">at</span>'
            f'<span style="font-weight:600;color:rgba(255,255,255,0.92)">{company_part}</span>'
            f"</div>"
        )
    elif title_part or company_part:
        meta_line = f'<div class="candidate-meta">{title_part or company_part}</div>'
    else:
        meta_line = ""

    location_line = (
        f'<div class="candidate-location">{_e(candidate.location)}</div>'
        if candidate.location
        else ""
    )

    # ── Badges ────────────────────────────────────────────────────────────
    level = (candidate.ai_career_level or "").lower()
    EXEC_LEVELS = {"c-suite", "executive", "vp", "director"}
    badges_html = ""
    if level in EXEC_LEVELS:
        badges_html += _badge("badge-exec", _e(candidate.ai_career_level))
    elif level:
        badges_html += _badge("badge-level", _e(candidate.ai_career_level.capitalize()))
    if candidate.ai_years_experience:
        badges_html += _badge(
            "badge-exp", f"{_e(candidate.ai_years_experience)} Yrs Exp"
        )
    for cert in ["CPA", "CFA", "CMA"]:
        if cert in (candidate.ai_certifications or "").upper():
            badges_html += _badge("badge-cert", cert)

    # ── Main sections ─────────────────────────────────────────────────────
    summary_section = _card(
        "AI Summary",
        (
            f'<p class="summary-text">{_clean_text(candidate.ai_summary, 700)}</p>'
            if candidate.ai_summary
            else ""
        ),
    )
    experience_section = _card(
        "Experience",
        (
            _parse_to_bullets(candidate.ai_experience, max_items=6)
            if candidate.ai_experience
            else ""
        ),
    )

    # Was: f'<p class="body-text">{_clean_text(candidate.ai_education, 450)}</p>'
    education_section = (
        _card(
            "Education",
            (
                _parse_to_bullets(candidate.ai_education, max_items=3)
                if candidate.ai_education
                else ""
            ),
        ),
    )

    # ── Contact ───────────────────────────────────────────────────────────
    contact_rows = '<div class="info-list">'
    if candidate.email:
        contact_rows += _info_row("Email", _e(candidate.email))
    if candidate.phone:
        contact_rows += _info_row("Phone", _e(candidate.phone))
    if candidate.linkedin_url:
        contact_rows += _info_row("LinkedIn", "View Profile")
    if candidate.location:
        contact_rows += _info_row("Location", _e(candidate.location))
    contact_rows += "</div>"
    contact_section = _card("Contact", contact_rows)

    # ── Skills ────────────────────────────────────────────────────────────
    skill_list = _parse_skills(candidate.ai_skills)
    skills_inner = (
        (
            '<div class="skills-wrap">'
            + "".join(f'<span class="skill-tag">{_e(s)}</span>' for s in skill_list)
            + "</div>"
        )
        if skill_list
        else ""
    )
    skills_section = _card("Skills", skills_inner)

    # ── Certifications — known ones as blue pills, else plain text ────────
    certs_inner = ""
    if candidate.ai_certifications:
        known = [
            c for c in ["CPA", "CFA", "CMA"] if c in candidate.ai_certifications.upper()
        ]
        if known:
            certs_inner = (
                '<div class="cert-badges">'
                + "".join(f'<span class="cert-badge">{c}</span>' for c in known)
                + "</div>"
            )
        else:
            certs_inner = f'<p class="body-text">{_clean_text(candidate.ai_certifications, 200)}</p>'
    certs_section = _card("Certifications", certs_inner)

    # ── Profile Details ───────────────────────────────────────────────────
    details_rows = '<div class="info-list">'
    if candidate.ai_career_level:
        details_rows += _info_row("Level", _e(candidate.ai_career_level.capitalize()))
    if candidate.ai_years_experience:
        details_rows += _info_row(
            "Experience", f"{_e(candidate.ai_years_experience)} years"
        )
    details_rows += _info_row(
        "Added",
        candidate.created_at.strftime("%b %d, %Y") if candidate.created_at else "—",
    )
    details_rows += "</div>"
    details_section = _card("Profile Details", details_rows)

    # ── Assemble ──────────────────────────────────────────────────────────
    html_string = _PDF_HTML.format(
        style=_PDF_STYLE.format(banner_style=banner_style),
        photo_tag=photo_tag,
        name=_e(candidate.name or "Unknown"),
        meta_line=meta_line,
        location_line=location_line,
        badges=badges_html,
        summary_section=summary_section,
        experience_section=experience_section,
        education_section=education_section,
        contact_section=contact_section,
        skills_section=skills_section,
        certs_section=certs_section,
        details_section=details_section,
        today=today_str,
    )

    # ── Render ────────────────────────────────────────────────────────────
    try:
        pdf_bytes = _render_pdf(html_string)
    except Exception as e:
        logger.error(f"PDF generation failed for candidate #{candidate_id}: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed.")

    safe_name = (candidate.name or "candidate").replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_RYZE_Profile.pdf"'
        },
    )
