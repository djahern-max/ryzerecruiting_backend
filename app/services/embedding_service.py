# app/services/embedding_service.py
"""
Embedding service for RYZE.ai RAG / PGVector functionality.

Uses OpenAI text-embedding-3-small (1536 dimensions).
Handles text composition from structured fields and batch embedding generation.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder

logger = logging.getLogger(__name__)

# Lazily initialized so the app doesn't crash if OPENAI_API_KEY is not yet set
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ---------------------------------------------------------------------------
# Text composition — what gets embedded for each entity type
# ---------------------------------------------------------------------------

def build_candidate_text(candidate: Candidate) -> Optional[str]:
    """
    Compose a rich text representation of a candidate from structured AI fields.
    This is what gets embedded — not the raw resume — so it's clean and consistent.
    """
    parts = []

    if candidate.name:
        parts.append(candidate.name)

    if candidate.current_title and candidate.current_company:
        parts.append(f"{candidate.current_title} at {candidate.current_company}")
    elif candidate.current_title:
        parts.append(candidate.current_title)

    if candidate.location:
        parts.append(f"Location: {candidate.location}")

    if candidate.ai_years_experience:
        parts.append(f"{candidate.ai_years_experience} years of experience")

    if candidate.ai_career_level:
        parts.append(f"Career level: {candidate.ai_career_level}")

    if candidate.ai_summary:
        parts.append(candidate.ai_summary)

    if candidate.ai_experience:
        parts.append(f"Work history: {candidate.ai_experience}")

    if candidate.ai_education:
        parts.append(f"Education: {candidate.ai_education}")

    if candidate.ai_certifications:
        parts.append(f"Certifications: {candidate.ai_certifications}")

    if candidate.ai_skills:
        skills = candidate.ai_skills if isinstance(candidate.ai_skills, list) else []
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")

    if candidate.notes:
        parts.append(f"Recruiter notes: {candidate.notes}")

    text = "\n".join(parts).strip()
    return text if len(text) > 20 else None


def build_employer_text(employer: EmployerProfile) -> Optional[str]:
    """
    Compose a rich text representation of an employer profile from AI intelligence fields.
    """
    parts = []

    if employer.company_name:
        parts.append(employer.company_name)

    if employer.ai_industry:
        parts.append(f"Industry: {employer.ai_industry}")

    if employer.ai_company_size:
        parts.append(f"Company size: {employer.ai_company_size}")

    if employer.ai_company_overview:
        parts.append(employer.ai_company_overview)

    if employer.ai_hiring_needs:
        try:
            needs = json.loads(employer.ai_hiring_needs)
            if isinstance(needs, list) and needs:
                parts.append(f"Hiring needs: {', '.join(needs)}")
        except (json.JSONDecodeError, TypeError):
            parts.append(f"Hiring needs: {employer.ai_hiring_needs}")

    if employer.ai_talking_points:
        try:
            points = json.loads(employer.ai_talking_points)
            if isinstance(points, list) and points:
                parts.append(f"Talking points: {' '.join(points)}")
        except (json.JSONDecodeError, TypeError):
            parts.append(f"Talking points: {employer.ai_talking_points}")

    if employer.recruiter_notes:
        parts.append(f"Recruiter notes: {employer.recruiter_notes}")

    if employer.raw_text:
        # Include raw source text as additional context if available
        parts.append(employer.raw_text[:2000])  # cap to avoid token limits

    text = "\n".join(parts).strip()
    return text if len(text) > 20 else None


def build_job_order_text(job_order: JobOrder) -> Optional[str]:
    """
    Compose a rich text representation of a job order.
    """
    parts = []

    if job_order.title:
        parts.append(f"Job title: {job_order.title}")

    if job_order.location:
        parts.append(f"Location: {job_order.location}")

    if job_order.salary_min and job_order.salary_max:
        parts.append(f"Salary range: ${job_order.salary_min:,} - ${job_order.salary_max:,}")
    elif job_order.salary_min:
        parts.append(f"Salary: ${job_order.salary_min:,}+")

    if job_order.requirements:
        parts.append(f"Requirements: {job_order.requirements}")

    if job_order.notes:
        parts.append(f"Notes: {job_order.notes}")

    if job_order.raw_text:
        parts.append(job_order.raw_text[:2000])

    text = "\n".join(parts).strip()
    return text if len(text) > 20 else None


# ---------------------------------------------------------------------------
# Core embedding call
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> Optional[list[float]]:
    """
    Generate a 1536-dimensional embedding vector for the given text.
    Returns None on failure so callers can decide how to handle it.
    """
    try:
        client = get_openai_client()
        # text-embedding-3-small: 1536 dims, ~$0.02 per million tokens
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text.replace("\n", " "),  # OpenAI recommends replacing newlines
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Background sync — processes all unembedded records
# ---------------------------------------------------------------------------

def sync_embeddings(batch_size: int = 50) -> dict:
    """
    Find all records without embeddings, generate and store them.
    Returns a summary dict for logging / API response.

    Designed to be called:
      - From the /api/search/embeddings/sync admin endpoint (on demand)
      - From a cron job / systemd timer (automated)
    """
    db: Session = SessionLocal()
    counts = {"candidates": 0, "employers": 0, "job_orders": 0, "errors": 0}

    try:
        # --- Candidates ---
        unembedded_candidates = (
            db.query(Candidate)
            .filter(Candidate.embedding.is_(None))
            .limit(batch_size)
            .all()
        )
        for candidate in unembedded_candidates:
            text = build_candidate_text(candidate)
            if not text:
                continue
            vector = generate_embedding(text)
            if vector:
                candidate.embedding = vector
                candidate.embedded_at = datetime.utcnow()
                counts["candidates"] += 1
            else:
                counts["errors"] += 1
        db.commit()

        # --- Employer Profiles ---
        unembedded_employers = (
            db.query(EmployerProfile)
            .filter(EmployerProfile.embedding.is_(None))
            .limit(batch_size)
            .all()
        )
        for employer in unembedded_employers:
            text = build_employer_text(employer)
            if not text:
                continue
            vector = generate_embedding(text)
            if vector:
                employer.embedding = vector
                employer.embedded_at = datetime.utcnow()
                counts["employers"] += 1
            else:
                counts["errors"] += 1
        db.commit()

        # --- Job Orders ---
        unembedded_jobs = (
            db.query(JobOrder)
            .filter(JobOrder.embedding.is_(None))
            .limit(batch_size)
            .all()
        )
        for job in unembedded_jobs:
            text = build_job_order_text(job)
            if not text:
                continue
            vector = generate_embedding(text)
            if vector:
                job.embedding = vector
                job.embedded_at = datetime.utcnow()
                counts["job_orders"] += 1
            else:
                counts["errors"] += 1
        db.commit()

        logger.info(
            f"Embedding sync complete: {counts['candidates']} candidates, "
            f"{counts['employers']} employers, {counts['job_orders']} job orders, "
            f"{counts['errors']} errors"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Embedding sync failed: {e}")
        raise
    finally:
        db.close()

    return counts
