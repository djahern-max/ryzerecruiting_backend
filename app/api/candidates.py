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
    UploadFile,
    status,
)
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
# List / get
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Create / update / delete
# ---------------------------------------------------------------------------


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
        .filter(Candidate.id == candidate_id, Candidate.tenant_id == 1)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    db.delete(candidate)
    db.commit()


# ---------------------------------------------------------------------------
# Parse — text paste
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Parse — file upload (PDF or DOCX)
# ---------------------------------------------------------------------------


@router.post("/parse-file", response_model=CandidateParseResponse)
async def parse_candidate_file(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    """
    Upload a PDF or Word document resume.
    Extracts text and passes through Claude parser.
    Returns structured fields for review — does NOT save to database.
    """
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
        if is_pdf:
            text = _extract_text_from_pdf(data)
        else:
            text = _extract_text_from_docx(data)
    except Exception as e:
        logger.error(f"File text extraction failed: {e}")
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from the file. Please try a different file or paste the text instead.",
        )

    if not text or len(text.strip()) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the file. Try pasting the content directly instead.",
        )

    logger.info(f"Extracted {len(text)} chars from {filename}")

    result = parse_candidate_profile(text)

    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the file. Please try again or paste the text manually.",
        )

    # Store raw extracted text so it saves with the candidate record
    result["linkedin_raw_text"] = text

    return result
