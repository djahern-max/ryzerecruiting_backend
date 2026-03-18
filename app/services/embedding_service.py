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
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
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

    if candidate.current_title:
        parts.append(f"Title: {candidate.current_title}")

    if candidate.current_company:
        parts.append(f"Company: {candidate.current_company}")

    if candidate.location:
        parts.append(f"Location: {candidate.location}")

    if candidate.ai_career_level:
        parts.append(f"Career level: {candidate.ai_career_level}")

    if candidate.ai_years_experience:
        parts.append(f"Years of experience: {candidate.ai_years_experience}")

    if candidate.ai_certifications:
        parts.append(f"Certifications: {candidate.ai_certifications}")

    if candidate.ai_summary:
        parts.append(candidate.ai_summary)

    if candidate.ai_experience:
        parts.append(candidate.ai_experience)

    if candidate.ai_education:
        parts.append(f"Education: {candidate.ai_education}")

    if candidate.ai_skills:
        try:
            skills = (
                json.loads(candidate.ai_skills)
                if isinstance(candidate.ai_skills, str)
                else candidate.ai_skills
            )
            if isinstance(skills, list) and skills:
                parts.append(f"Skills: {', '.join(skills)}")
        except (json.JSONDecodeError, TypeError):
            parts.append(f"Skills: {candidate.ai_skills}")

    # Include raw source text as additional context
    raw = candidate.linkedin_raw_text
    if raw:
        parts.append(raw[:2000])

    text = "\n".join(parts).strip()
    return text if len(text) > 20 else None


def build_employer_text(employer: EmployerProfile) -> Optional[str]:
    """
    Compose a rich text representation of an employer profile.
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

    # Include raw source text if available
    raw = getattr(employer, "raw_text", None)
    if raw:
        parts.append(raw[:2000])

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
        parts.append(
            f"Salary range: ${job_order.salary_min:,} - ${job_order.salary_max:,}"
        )
    elif job_order.salary_min:
        parts.append(f"Salary: ${job_order.salary_min:,}+")

    if job_order.requirements:
        parts.append(f"Requirements: {job_order.requirements}")

    if job_order.notes:
        parts.append(f"Notes: {job_order.notes}")

    # Include raw source text if available
    raw = getattr(job_order, "raw_text", None)
    if raw:
        parts.append(raw[:2000])

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
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-record background embedding helpers
# Called as FastAPI BackgroundTasks after POST/PATCH saves.
# Each opens its own DB session — safe to run after the request completes.
# ---------------------------------------------------------------------------


def embed_candidate_background(candidate_id: int) -> None:
    """
    Generate and store an embedding for a single candidate.
    Designed to run as a FastAPI BackgroundTask.
    """
    db: Session = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            logger.warning(
                f"embed_candidate_background: candidate #{candidate_id} not found"
            )
            return

        text = build_candidate_text(candidate)
        if not text:
            logger.warning(
                f"embed_candidate_background: no embeddable text for candidate #{candidate_id}"
            )
            return

        vector = generate_embedding(text)
        if vector:
            candidate.embedding = vector
            candidate.embedded_at = datetime.utcnow()
            db.commit()
            logger.info(f"Embedded candidate #{candidate_id} ({candidate.name})")
        else:
            logger.error(
                f"embed_candidate_background: embedding failed for candidate #{candidate_id}"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"embed_candidate_background error for #{candidate_id}: {e}")
    finally:
        db.close()


def embed_employer_background(profile_id: int) -> None:
    """
    Generate and store an embedding for a single employer profile.
    Designed to run as a FastAPI BackgroundTask.
    """
    db: Session = SessionLocal()
    try:
        employer = (
            db.query(EmployerProfile).filter(EmployerProfile.id == profile_id).first()
        )
        if not employer:
            logger.warning(
                f"embed_employer_background: employer #{profile_id} not found"
            )
            return

        text = build_employer_text(employer)
        if not text:
            logger.warning(
                f"embed_employer_background: no embeddable text for employer #{profile_id}"
            )
            return

        vector = generate_embedding(text)
        if vector:
            employer.embedding = vector
            employer.embedded_at = datetime.utcnow()
            db.commit()
            logger.info(f"Embedded employer #{profile_id} ({employer.company_name})")
        else:
            logger.error(
                f"embed_employer_background: embedding failed for employer #{profile_id}"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"embed_employer_background error for #{profile_id}: {e}")
    finally:
        db.close()


def embed_job_order_background(job_order_id: int) -> None:
    """
    Generate and store an embedding for a single job order.
    Designed to run as a FastAPI BackgroundTask.
    """
    db: Session = SessionLocal()
    try:
        job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
        if not job_order:
            logger.warning(
                f"embed_job_order_background: job order #{job_order_id} not found"
            )
            return

        text = build_job_order_text(job_order)
        if not text:
            logger.warning(
                f"embed_job_order_background: no embeddable text for job order #{job_order_id}"
            )
            return

        vector = generate_embedding(text)
        if vector:
            job_order.embedding = vector
            job_order.embedded_at = datetime.utcnow()
            db.commit()
            logger.info(f"Embedded job order #{job_order_id} ({job_order.title})")
        else:
            logger.error(
                f"embed_job_order_background: embedding failed for job order #{job_order_id}"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"embed_job_order_background error for #{job_order_id}: {e}")
    finally:
        db.close()


def build_booking_text(booking) -> Optional[str]:
    """
    Compose embeddable text from all available meeting intelligence fields.

    Concatenates summary, next steps, keywords, and transcript so the
    RAG search has maximum signal — exact dialogue becomes searchable,
    not just the AI summary paragraph.

    Transcript is truncated to ~6000 chars to stay within embedding
    token limits (text-embedding-3-small supports ~8191 tokens).
    """
    parts = []

    if booking.company_name:
        parts.append(f"Company: {booking.company_name}")

    if booking.employer_name:
        parts.append(f"Contact: {booking.employer_name}")

    if booking.date:
        parts.append(f"Meeting date: {booking.date}")

    if booking.call_notes:
        parts.append(f"Call notes: {booking.call_notes}")

    if booking.meeting_summary:
        parts.append(f"Meeting summary:\n{booking.meeting_summary}")

    if booking.meeting_next_steps:
        parts.append(f"Next steps:\n{booking.meeting_next_steps}")

    if booking.meeting_keywords:
        parts.append(f"Keywords: {booking.meeting_keywords}")

    # Transcript last — it's the longest and most detailed.
    # Truncate to stay within embedding token limits.
    if booking.meeting_transcript:
        transcript_excerpt = booking.meeting_transcript[:6000]
        if len(booking.meeting_transcript) > 6000:
            transcript_excerpt += "\n[transcript truncated]"
        parts.append(f"Meeting transcript:\n{transcript_excerpt}")

    text = "\n\n".join(parts).strip()
    return text if len(text) > 20 else None


def embed_booking_background(booking_id: int) -> None:
    """
    Generate and store an embedding for a single booking's meeting notes.
    Designed to run as a FastAPI BackgroundTask.
    """
    from app.models.booking import Booking

    db: Session = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            logger.warning(f"embed_booking_background: booking #{booking_id} not found")
            return

        text = build_booking_text(booking)
        if not text:
            logger.warning(
                f"embed_booking_background: no embeddable text for booking #{booking_id}"
            )
            return

        vector = generate_embedding(text)
        if vector:
            booking.embedding = vector
            booking.embedded_at = datetime.utcnow()
            db.commit()
            logger.info(f"Embedded booking #{booking_id} ({booking.company_name})")
        else:
            logger.error(
                f"embed_booking_background: embedding failed for booking #{booking_id}"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"embed_booking_background error for #{booking_id}: {e}")
    finally:
        db.close()


def backfill_bookings() -> dict:
    """
    One-time backfill: embed all bookings that have meeting_summary but no embedding.
    Run after seeding demo data.
    """
    from app.models.booking import Booking

    db: Session = SessionLocal()
    count, errors = 0, 0
    try:
        bookings = (
            db.query(Booking)
            .filter(Booking.meeting_summary.isnot(None))
            .filter(Booking.embedding.is_(None))
            .all()
        )
        for booking in bookings:
            text = build_booking_text(booking)
            if not text:
                continue
            vector = generate_embedding(text)
            if vector:
                booking.embedding = vector
                booking.embedded_at = datetime.utcnow()
                count += 1
            else:
                errors += 1
        db.commit()
        logger.info(f"Booking backfill complete: {count} embedded, {errors} errors")
    except Exception as e:
        db.rollback()
        logger.error(f"Booking backfill failed: {e}")
    finally:
        db.close()
    return {"embedded": count, "errors": errors}


# ---------------------------------------------------------------------------
# Batch sync — used by the /embeddings/sync admin endpoints
# ---------------------------------------------------------------------------


def sync_embeddings(batch_size: int = 50) -> dict:
    """
    Find all records without embeddings and generate them in batches.
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
