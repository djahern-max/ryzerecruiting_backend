# app/api/candidates.py

import logging
import io
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

# ── PDF template: HTML/CSS + pure helpers live in their own module ────────────
from app.api.candidate_pdf_template import (
    PDF_STYLE,
    PDF_HTML,
    render_pdf,
    pdf_card,
    pdf_info_row,
    pdf_badge,
    pdf_e,
    pdf_clean_text,
    pdf_parse_skills,
    pdf_parse_to_bullets,
)

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


# ─────────────────────────────────────────────────────────────────────────────
# Candidate-self routes  (/me must come before /{id})
# ─────────────────────────────────────────────────────────────────────────────


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
            .filter(JobOrder.tenant_id == tenant_id, JobOrder.status == "open")
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
            SELECT id, (embedding <-> '{vector_str}'::vector) AS distance
            FROM job_orders
            WHERE tenant_id = :tenant
            AND status = 'open'
            AND embedding IS NOT NULL
            ORDER BY distance
            LIMIT :lim
        """)
        rows = db.execute(
            sql,
            {"tenant": tenant_id, "lim": limit},
        ).fetchall()
    except Exception:
        db.rollback()
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


@router.post("/me/photo")
async def upload_my_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")

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
        data, f"candidates/{candidate.id}/photo", unique_name, file.content_type
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Photo upload failed.")

    candidate.photo_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()
    return {"photo_url": cdn_url}


@router.post("/me/banner")
async def upload_my_banner(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated_user),
):
    candidate = _resolve_candidate_for_user(db, current_user)
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate profile found.")

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
        data, f"candidates/{candidate.id}/banner", unique_name, file.content_type
    )
    if not cdn_url:
        raise HTTPException(status_code=500, detail="Banner upload failed.")

    candidate.banner_url = cdn_url
    candidate.updated_at = datetime.utcnow()
    db.commit()
    return {"banner_url": cdn_url}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list / search / duplicate check
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Admin — CRUD
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Admin — AI parse
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Admin — Embeddings
# ─────────────────────────────────────────────────────────────────────────────


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
            Candidate.tenant_id == _tenant(current_user),
            Candidate.embedding.is_(None),
        )
        .all()
    )
    count = len(unembedded)
    for c in unembedded:
        background_tasks.add_task(embed_candidate_background, c.id)
    return {"queued": count, "message": f"{count} candidate(s) queued for indexing"}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — Photo & Banner upload
# ─────────────────────────────────────────────────────────────────────────────


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
# PDF Export
#
# HTML/CSS template and pure helpers live in candidate_pdf_template.py.
# This route owns: DB query, tenant check, data assembly, StreamingResponse.
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

    # ── Banner style ──────────────────────────────────────────────────────
    if candidate.banner_url:
        banner_style = f"url('{candidate.banner_url}')"
    else:
        banner_style = "linear-gradient(135deg, #0f2444 0%, #1a3a6b 60%, #1e4a8a 100%)"

    # ── Avatar / photo tag ────────────────────────────────────────────────
    if candidate.photo_url:
        photo_tag = f'<img src="{candidate.photo_url}" alt="" />'
    else:
        initial = (candidate.name or "?")[0].upper()
        photo_tag = f'<span style="font-size:28px;font-weight:800;color:#fff;letter-spacing:-1px;">{initial}</span>'

    # ── Name meta line (title · company) ─────────────────────────────────
    meta_parts = []
    if candidate.current_title:
        meta_parts.append(pdf_e(candidate.current_title))
    if candidate.current_company:
        meta_parts.append(f"<strong>{pdf_e(candidate.current_company)}</strong>")
    if meta_parts:
        divider = ' <span class="meta-divider">·</span> '
        meta_line = f'<div class="candidate-meta">{divider.join(meta_parts)}</div>'
    else:
        meta_line = ""

    # ── Location line ─────────────────────────────────────────────────────
    if candidate.location:
        location_line = (
            f'<div class="candidate-location">{pdf_e(candidate.location)}</div>'
        )
    else:
        location_line = ""

    # ── Badges ────────────────────────────────────────────────────────────
    badges_html = ""
    if candidate.ai_career_level:
        level = candidate.ai_career_level.lower()
        cls = "badge-exec" if level == "executive" else "badge-level"
        badges_html += pdf_badge(cls, pdf_e(candidate.ai_career_level.capitalize()))
    if candidate.ai_years_experience:
        badges_html += pdf_badge(
            "badge-exp", pdf_e(f"{candidate.ai_years_experience} yrs exp")
        )
    if candidate.ai_certifications:
        certs_upper = candidate.ai_certifications.upper()
        for cert in ("CPA", "CFA", "CMA"):
            if cert in certs_upper:
                badges_html += pdf_badge("badge-cert", cert)

    # ── Main column sections ──────────────────────────────────────────────
    summary_section = pdf_card(
        "About",
        (
            f'<p class="summary-text">{pdf_clean_text(candidate.ai_summary, 600)}</p>'
            if candidate.ai_summary
            else ""
        ),
    )
    experience_section = pdf_card(
        "Experience", pdf_parse_to_bullets(candidate.ai_experience, 6)
    )
    education_section = pdf_card(
        "Education", pdf_parse_to_bullets(candidate.ai_education, 3)
    )

    # ── Side column sections ──────────────────────────────────────────────
    contact_rows = '<div class="info-list">'
    if candidate.email:
        contact_rows += pdf_info_row("Email", pdf_e(candidate.email))
    if candidate.phone:
        contact_rows += pdf_info_row("Phone", pdf_e(candidate.phone))
    if candidate.linkedin_url:
        contact_rows += pdf_info_row("LinkedIn", "linkedin.com/in/…")
    contact_rows += "</div>"
    contact_section = pdf_card("Contact", contact_rows)

    skills_list = pdf_parse_skills(candidate.ai_skills)
    if skills_list:
        tags = "".join(
            f'<span class="skill-tag">{pdf_e(s)}</span>' for s in skills_list
        )
        skills_inner = f'<div class="skills-wrap">{tags}</div>'
    else:
        skills_inner = ""
    skills_section = pdf_card("Skills", skills_inner)

    if candidate.ai_certifications:
        certs_upper = candidate.ai_certifications.upper()
        known = [c for c in ("CPA", "CFA", "CMA") if c in certs_upper]
        if known:
            certs_inner = (
                '<div class="cert-badges">'
                + "".join(f'<span class="cert-badge">{c}</span>' for c in known)
                + "</div>"
            )
        else:
            certs_inner = f'<p class="body-text">{pdf_clean_text(candidate.ai_certifications, 200)}</p>'
    else:
        certs_inner = ""
    certs_section = pdf_card("Certifications", certs_inner)

    details_rows = '<div class="info-list">'
    if candidate.ai_career_level:
        details_rows += pdf_info_row(
            "Level", pdf_e(candidate.ai_career_level.capitalize())
        )
    if candidate.ai_years_experience:
        details_rows += pdf_info_row(
            "Experience", f"{pdf_e(candidate.ai_years_experience)} years"
        )
    details_rows += pdf_info_row(
        "Added",
        candidate.created_at.strftime("%b %d, %Y") if candidate.created_at else "—",
    )
    details_rows += "</div>"
    details_section = pdf_card("Profile Details", details_rows)

    # ── Assemble HTML ─────────────────────────────────────────────────────
    html_string = PDF_HTML.format(
        style=PDF_STYLE.format(banner_style=banner_style),
        photo_tag=photo_tag,
        name=pdf_e(candidate.name or "Unknown"),
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
        pdf_bytes = render_pdf(html_string)
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
