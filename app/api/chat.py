# app/api/chat.py
import json
import logging
from datetime import date, datetime, timedelta
from typing import Iterator, List, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.deps import RYZE_TENANT, get_current_admin_tenant

from app.api.bookings import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.models.user import User
from app.services.embedding_service import generate_embedding
from app.services.branding import get_branding, TenantBranding
from app.services.matching import compute_match_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []


# ---------------------------------------------------------------------------
# Tool status messages — shown in the UI during the tool-call phase
# ---------------------------------------------------------------------------

TOOL_STATUS_MESSAGES = {
    "search_candidates": "Searching candidate database...",
    "search_employers": "Searching employer profiles...",
    "search_job_orders": "Searching job orders...",
    "get_todays_meetings": "Checking today's schedule...",
    "get_meetings_by_date": "Checking your calendar...",
    "get_candidate_by_name": "Looking up candidate...",
    "get_employer_by_name": "Looking up employer...",
    "match_candidates_to_job": "Matching candidates to role...",
    "search_meeting_notes": "Searching meeting notes...",
    "get_candidate_calls": "Looking up call history...",
    "get_call_transcript": "Reading the call transcript...",
    "match_jobs_to_candidate": "Matching open roles to candidate...",
}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    # In TOOLS list — add this entry:
    {
        "name": "get_candidate_calls",
        "description": (
            "Look up all calls and meetings associated with a specific candidate by name. "
            "Use when asked about a call with a candidate, what was discussed with a candidate, "
            "meeting notes for a candidate, or any question about a specific person's call history. "
            "Returns bookings linked to the candidate with the AI meeting summary, keywords, and "
            "call notes. Each call carries a has_transcript flag — if the recruiter needs the "
            "detail of what was actually said, follow up with get_call_transcript using that "
            "call's id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The candidate's name or partial name",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_candidates",
        "description": (
            "Semantic vector search over all candidate profiles. "
            "Use for queries like: find CPAs, who has Big 4 experience, "
            "senior candidates in Boston, candidates with NetSuite skills, "
            "recommend candidates for a role. Returns ranked list with scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query describing the ideal candidate",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_employers",
        "description": (
            "Semantic vector search over employer intelligence profiles. "
            "Use for queries about companies, industries, hiring needs, or employer research."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query about an employer or company type",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_job_orders",
        "description": (
            "Semantic vector search over open job orders. "
            "Use for queries about open roles, job requirements, or salary ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query about a job or role",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_todays_meetings",
        "description": (
            "Returns all bookings scheduled for today. "
            "Use when asked about today's calls, meetings, or schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_meetings_by_date",
        "description": (
            "Returns bookings for a specific date or date range. "
            "Use when asked about meetings on a specific day or upcoming schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (optional, defaults to start_date)",
                },
            },
            "required": ["start_date"],
        },
    },
    {
        "name": "get_candidate_by_name",
        "description": (
            "Direct lookup of a candidate by name. "
            "Use when the recruiter asks about a specific named candidate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The candidate's name or partial name to search for",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_employer_by_name",
        "description": (
            "Direct lookup of an employer profile by company name. "
            "Use when asked about a specific company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The company name or partial name to search for",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "match_candidates_to_job",
        "description": (
            "Find the best matching candidates for a specific job order using vector similarity. "
            "Use when asked to match candidates to a role or find the best fit for a position."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_title": {
                    "type": "string",
                    "description": "The job title or role description to match candidates against",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["job_title"],
        },
    },
    {
        "name": "search_meeting_notes",
        "description": (
            "Semantic vector search over Zoom meeting notes and call summaries. "
            "Use when asked about past calls, what was discussed with a company, "
            "follow-ups from meetings, or any question about meeting history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query about meeting notes or call history",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_call_transcript",
        "description": (
            "Fetch the full transcript of one specific call, as speaker turns. "
            "Only call this when the recruiter asks about the detail of what was "
            "actually said — the meeting summary is usually enough. Requires a "
            "booking_id from get_candidate_calls or get_meetings_by_date. "
            "The transcript is raw source material: synthesize it, never quote it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {
                    "type": "integer",
                    "description": "The booking/call id whose transcript to fetch",
                },
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "match_jobs_to_candidate",
        "description": (
            "Find open job orders ranked against one specific candidate's stored "
            "profile embedding. Use for queries like 'show me matches for <name>', "
            "'what roles fit <name>', or 'which open jobs should we pitch to <name>'. "
            "This ranks jobs for a named candidate — for the reverse (ranking "
            "candidates for a job), use match_candidates_to_job instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The candidate's name or partial name",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution functions
# ---------------------------------------------------------------------------


def _vector_search(
    db,
    table_name: str,
    query: str,
    limit: int,
    tenant_id: str = RYZE_TENANT,  # EP16: added tenant_id param
) -> list:
    """
    Run cosine similarity search using raw SQL.
    EP16: scoped to a single tenant via WHERE tenant_id = :tenant_id.
    """
    from app.services.embedding_service import generate_embedding

    embedding = generate_embedding(query)
    if not embedding:
        return []

    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    sql = text(f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM {table_name}
        WHERE embedding IS NOT NULL
          AND tenant_id = :tenant_id
        ORDER BY distance
        LIMIT :limit
        """)
    rows = db.execute(sql, {"tenant_id": tenant_id, "limit": limit}).fetchall()
    return rows


def tool_search_candidates(
    db, query: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    from app.models.candidate import Candidate

    rows = _vector_search(db, "candidates", query, limit, tenant_id)  # EP16
    if not rows:
        return {"candidates": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    candidates = (
        db.query(Candidate)
        .filter(Candidate.id.in_(ids), Candidate.tenant_id == tenant_id)  # EP16
        .all()
    )
    candidate_map = {c.id: c for c in candidates}

    results = []
    for cid in ids:
        if cid not in candidate_map:
            continue
        c = candidate_map[cid]
        results.append(
            {
                "id": c.id,
                "name": c.name,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "location": c.location,
                "ai_summary": c.ai_summary,
                "ai_career_level": c.ai_career_level,
                "ai_certifications": c.ai_certifications,
                "ai_years_experience": c.ai_years_experience,
                "score": round(max(0.0, 1.0 - float(distances[cid])), 4),
            }
        )

    return {"candidates": results, "count": len(results)}


def tool_search_employers(
    db, query: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    from app.models.employer_profile import EmployerProfile

    rows = _vector_search(db, "employer_profiles", query, limit, tenant_id)  # EP16
    if not rows:
        return {"employers": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    employers = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.id.in_(ids), EmployerProfile.tenant_id == tenant_id
        )  # EP16
        .all()
    )
    employer_map = {e.id: e for e in employers}

    results = []
    for eid in ids:
        if eid not in employer_map:
            continue
        e = employer_map[eid]
        results.append(
            {
                "id": e.id,
                "company_name": e.company_name,
                "ai_industry": e.ai_industry,
                "ai_company_overview": e.ai_company_overview,
                "ai_hiring_needs": e.ai_hiring_needs,
                "ai_talking_points": e.ai_talking_points,
                "relationship_status": e.relationship_status,
                "score": round(max(0.0, 1.0 - float(distances[eid])), 4),
            }
        )

    return {"employers": results, "count": len(results)}


def tool_search_job_orders(
    db, query: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    from app.models.job_order import JobOrder

    rows = _vector_search(db, "job_orders", query, limit, tenant_id)  # EP16
    if not rows:
        return {"job_orders": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    jobs = (
        db.query(JobOrder)
        .filter(JobOrder.id.in_(ids), JobOrder.tenant_id == tenant_id)  # EP16
        .all()
    )
    job_map = {j.id: j for j in jobs}

    results = []
    for jid in ids:
        if jid not in job_map:
            continue
        j = job_map[jid]
        results.append(
            {
                "id": j.id,
                "title": j.title,
                "location": j.location,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "requirements": j.requirements,
                "status": j.status,
                "score": round(max(0.0, 1.0 - float(distances[jid])), 4),
            }
        )

    return {"job_orders": results, "count": len(results)}


def tool_get_todays_meetings(db: Session, tenant_id: str = RYZE_TENANT) -> dict:
    today = date.today()
    bookings = (
        db.query(Booking)
        .filter(Booking.date == today.isoformat(), Booking.tenant_id == tenant_id)
        .order_by(Booking.time_slot)
        .all()
    )

    results = []
    for b in bookings:
        results.append(
            {
                "id": b.id,
                "employer_name": b.employer_name,
                "company_name": b.company_name,
                "date": str(b.date),
                "time_slot": b.time_slot,
                "status": b.status,
                "meeting_url": b.meeting_url,
                "booking_type": b.booking_type,
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_meetings_by_date(
    db: Session,
    start_date: str,
    end_date: Optional[str] = None,
    tenant_id: str = RYZE_TENANT,
) -> dict:
    end = end_date or start_date
    bookings = (
        db.query(Booking)
        .filter(
            Booking.date >= start_date,
            Booking.date <= end,
            Booking.tenant_id == tenant_id,
        )
        .order_by(Booking.date, Booking.time_slot)
        .all()
    )

    results = []
    for b in bookings:
        results.append(
            {
                "id": b.id,
                "employer_name": b.employer_name,
                "company_name": b.company_name,
                "date": str(b.date),
                "time_slot": b.time_slot,
                "status": b.status,
                "meeting_url": b.meeting_url,
                "booking_type": b.booking_type,
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_candidate_by_name(
    db: Session, name: str, tenant_id: str = RYZE_TENANT
) -> dict:
    candidates = (
        db.query(Candidate)
        .filter(Candidate.name.ilike(f"%{name}%"), Candidate.tenant_id == tenant_id)
        .limit(5)
        .all()
    )

    if not candidates:
        return {"candidates": [], "count": 0}

    results = []
    for c in candidates:
        results.append(
            {
                "id": c.id,
                "name": c.name,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "location": c.location,
                "ai_summary": c.ai_summary,
                "ai_career_level": c.ai_career_level,
                "ai_certifications": c.ai_certifications,
                "ai_years_experience": c.ai_years_experience,
                "has_transcript": bool(c.meeting_transcript),
            }
        )

    return {"candidates": results, "count": len(results)}


def tool_get_employer_by_name(
    db: Session, name: str, tenant_id: str = RYZE_TENANT
) -> dict:
    employers = (
        db.query(EmployerProfile)
        .filter(
            EmployerProfile.company_name.ilike(f"%{name}%"),
            EmployerProfile.tenant_id == tenant_id,
        )
        .limit(5)
        .all()
    )

    if not employers:
        return {"employers": [], "count": 0}

    results = []
    for e in employers:
        hiring_needs = []
        if e.ai_hiring_needs:
            try:
                hiring_needs = json.loads(e.ai_hiring_needs)
            except Exception:
                pass

        talking_points = []
        if e.ai_talking_points:
            try:
                talking_points = json.loads(e.ai_talking_points)
            except Exception:
                pass

        results.append(
            {
                "id": e.id,
                "company_name": e.company_name,
                "website_url": e.website_url,
                "ai_industry": e.ai_industry,
                "ai_company_size": e.ai_company_size,
                "ai_company_overview": e.ai_company_overview,
                "ai_hiring_needs": hiring_needs,
                "ai_talking_points": talking_points,
                "ai_red_flags": e.ai_red_flags,
                "relationship_status": e.relationship_status,
                "recruiter_notes": e.recruiter_notes,
            }
        )

    return {"employers": results, "count": len(results)}


def tool_match_candidates_to_job(
    db: Session, job_title: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    return tool_search_candidates(db, job_title, limit, tenant_id)


def tool_search_meeting_notes(
    db: Session, query: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    rows = _vector_search(db, "bookings", query, limit, tenant_id)
    if not rows:
        return {"meetings": [], "count": 0}

    ids = [r[0] for r in rows]
    bookings = (
        db.query(Booking)
        .filter(Booking.id.in_(ids), Booking.tenant_id == tenant_id)
        .all()
    )

    results = []
    for b in bookings:
        results.append(
            {
                "id": b.id,
                "company_name": b.company_name,
                "employer_name": b.employer_name,
                "date": str(b.date),
                "time_slot": b.time_slot,
                "meeting_summary": b.meeting_summary,
                "call_notes": b.call_notes,
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_candidate_calls(
    db: Session, name: str, tenant_id: str = RYZE_TENANT
) -> dict:
    # First find the candidate(s) matching the name
    candidates = (
        db.query(Candidate)
        .filter(Candidate.name.ilike(f"%{name}%"), Candidate.tenant_id == tenant_id)
        .limit(5)
        .all()
    )

    if not candidates:
        return {
            "calls": [],
            "count": 0,
            "message": f"No candidate found matching '{name}'",
        }

    candidate_ids = [c.id for c in candidates]
    candidate_names = {c.id: c.name for c in candidates}

    # Find all bookings linked to those candidates via candidate_id FK
    bookings = (
        db.query(Booking)
        .filter(
            Booking.candidate_id.in_(candidate_ids),
            Booking.tenant_id == tenant_id,
        )
        .order_by(Booking.date.desc())
        .all()
    )

    # Also search by employer_name as a fallback (some bookings may not have candidate_id set)
    name_matched_bookings = (
        db.query(Booking)
        .filter(
            Booking.employer_name.ilike(f"%{name}%"),
            Booking.tenant_id == tenant_id,
            Booking.id.notin_([b.id for b in bookings]),  # avoid dupes
        )
        .order_by(Booking.date.desc())
        .all()
    )

    all_bookings = bookings + name_matched_bookings

    if not all_bookings:
        candidate_name = candidates[0].name if candidates else name
        return {
            "calls": [],
            "count": 0,
            "candidate_found": True,
            "candidate_name": candidate_name,
            "message": f"Found candidate '{candidate_name}' but no calls are on record yet.",
        }

    results = []
    for b in all_bookings:
        results.append(
            {
                "id": b.id,
                "candidate_name": candidate_names.get(b.candidate_id, b.employer_name),
                "date": str(b.date),
                "time_slot": b.time_slot,
                "booking_type": b.booking_type,
                "status": b.status,
                "call_outcome": b.call_outcome,
                "call_notes": b.call_notes,
                "meeting_summary": b.meeting_summary,
                "meeting_next_steps": b.meeting_next_steps,
                "meeting_keywords": b.meeting_keywords,
                "has_transcript": bool(b.meeting_transcript),
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_call_transcript(
    db: Session, booking_id: int, tenant_id: str = RYZE_TENANT
) -> dict:
    from app.services.transcript import parse_transcript

    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id, Booking.tenant_id == tenant_id)
        .first()
    )
    if not booking:
        return {"error": f"No call found with id {booking_id}."}

    turns = parse_transcript(booking.meeting_transcript)
    if not turns:
        return {"error": "No transcript on record for that call."}

    return {
        "booking_id": booking.id,
        "name": booking.employer_name,
        "date": str(booking.date),
        "turns": turns,
    }


def tool_match_jobs_to_candidate(
    db: Session, name: str, limit: int = 5, tenant_id: str = RYZE_TENANT
) -> dict:
    """
    Rank open job orders against ONE candidate's stored profile embedding.
    """
    candidates = (
        db.query(Candidate)
        .filter(Candidate.name.ilike(f"%{name}%"), Candidate.tenant_id == tenant_id)
        .order_by(Candidate.id.desc())
        .limit(5)
        .all()
    )

    if not candidates:
        return {"error": f"No candidate found matching '{name}'."}

    candidate = candidates[0]

    note = None
    if len(candidates) > 1:
        note = (
            f"'{name}' matched {len(candidates)} candidates; used {candidate.name} "
            f"(id {candidate.id}), the most recently added match."
        )

    if candidate.embedding is None:
        return {
            "error": (
                f"{candidate.name} does not have a profile embedding yet, "
                "so job matches can't be ranked for them."
            )
        }

    vector_str = "[" + ",".join(str(v) for v in candidate.embedding) + "]"
    sql = text(f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM job_orders
        WHERE tenant_id = :tenant
        AND status = 'open'
        AND embedding IS NOT NULL
        ORDER BY distance
        LIMIT :lim
        """)
    try:
        rows = db.execute(sql, {"tenant": tenant_id, "lim": limit}).fetchall()
    except Exception:
        db.rollback()
        return {"error": "Job matching failed due to a database error."}

    ids = [r[0] for r in rows]
    distances = {r[0]: float(r[1]) for r in rows}
    jobs = (
        db.query(JobOrder)
        .filter(JobOrder.id.in_(ids), JobOrder.tenant_id == tenant_id)
        .all()
    )
    job_map = {j.id: j for j in jobs}

    results = []
    for jid in ids:
        if jid not in job_map:
            continue
        j = job_map[jid]
        results.append(
            {
                "id": j.id,
                "title": j.title,
                "location": j.location,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "requirements": j.requirements,
                "status": j.status,
                "match_score": compute_match_score(distances[jid]),
            }
        )

    result = {
        "job_orders": results,
        "count": len(results),
        "candidate_name": candidate.name,
    }
    if note:
        result["note"] = note
    return result


# ---------------------------------------------------------------------------
# Tool dispatch — EP16: tenant_id threaded through every tool call
# ---------------------------------------------------------------------------


def make_tool_dispatch(tenant_id: str) -> dict:
    return {
        "search_candidates": lambda db, inp: tool_search_candidates(
            db, inp["query"], inp.get("limit", 5), tenant_id
        ),
        "search_employers": lambda db, inp: tool_search_employers(
            db, inp["query"], inp.get("limit", 5), tenant_id
        ),
        "search_job_orders": lambda db, inp: tool_search_job_orders(
            db, inp["query"], inp.get("limit", 5), tenant_id
        ),
        "get_todays_meetings": lambda db, inp: tool_get_todays_meetings(db, tenant_id),
        "get_meetings_by_date": lambda db, inp: tool_get_meetings_by_date(
            db, inp["start_date"], inp.get("end_date"), tenant_id
        ),
        "get_candidate_by_name": lambda db, inp: tool_get_candidate_by_name(
            db, inp["name"], tenant_id
        ),
        "get_employer_by_name": lambda db, inp: tool_get_employer_by_name(
            db, inp["name"], tenant_id
        ),
        "match_candidates_to_job": lambda db, inp: tool_match_candidates_to_job(
            db, inp["job_title"], inp.get("limit", 5), tenant_id
        ),
        "search_meeting_notes": lambda db, inp: tool_search_meeting_notes(
            db, inp["query"], inp.get("limit", 5), tenant_id
        ),
        "get_candidate_calls": lambda db, inp: tool_get_candidate_calls(
            db, inp["name"], tenant_id
        ),
        "get_call_transcript": lambda db, inp: tool_get_call_transcript(
            db, inp["booking_id"], tenant_id
        ),
        "match_jobs_to_candidate": lambda db, inp: tool_match_jobs_to_candidate(
            db, inp["name"], inp.get("limit", 5), tenant_id
        ),
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# System prompt — built per request, scoped to the calling tenant
# ---------------------------------------------------------------------------


def build_system_prompt(branding: TenantBranding) -> str:
    """
    Resolve the Intelligence system prompt for one request.

    Deliberately a function, not a module constant, for two reasons:
      1. The firm identity and vertical belong to the tenant, not to RYZE.
         A module-level constant hardcoded "accounting and finance" and made
         the model reject any candidate outside that vertical as out of scope.
      2. date.today() in a module-level f-string is evaluated ONCE at import,
         so a long-running gunicorn worker froze "today" at boot time.

    `specialty` is read with getattr so this works before the tenants column
    exists — same forward-compatible pattern get_branding() uses.
    """
    firm = branding.brand_name
    specialty = getattr(branding, "specialty", None)

    focus = (
        f"{firm} specializes in {specialty}."
        if specialty
        else (
            f"{firm} recruits across whatever industries, roles, and seniority levels "
            "appear in its own data. Do not assume a vertical. Never describe a person "
            "or company as outside the firm's focus, wheelhouse, or specialty."
        )
    )

    return f"""You are {firm} Intelligence — the AI assistant for {firm}, a recruiting firm.

{focus}

You have direct access to this firm's live database through a set of search tools.
Every record you can retrieve belongs to {firm} and is there on purpose.

Today's date is {date.today().strftime("%B %d, %Y")}.

RESPONSE STYLE — follow these rules strictly:
- Respond in the voice of an experienced recruiter at this firm.
- Lead with 2–4 sentences of natural, well-written prose that directly answers the question.
- Write as if a senior recruiter is replying to a colleague — confident, specific, and conversational.
- Never use markdown headers, bullet points, numbered lists, or field labels in your prose.
- Never use preamble like "Great question", "Based on your database...", or "I found X results."
- Mention retrieved candidates and employers naturally by name within the prose.
- If no relevant records are found, say so naturally in one sentence. Do not fabricate names or data.
- Never repeat information already stated in the same response.
- For meeting/schedule questions, prose is sufficient — no cards needed.

HANDLING RECORDS — strict:
- Report what a record contains. Never editorialize about whether it belongs in the
  database, whether it is real, test, seed, or demo data, or whether the person is a
  legitimate candidate. That judgment is not yours to make.
- Never volunteer doubts about a record's provenance unless the recruiter asks directly.

TRANSCRIPTS — strict:
- Call transcripts are raw source material for you to read, never content to output.
- Never quote, paste, or reproduce transcript text verbatim, in whole or in part.
  Always synthesize in your own words.
- Ignore recording logistics, scheduling talk, technical difficulties, greetings,
  sign-offs, and off-topic chatter. Report only the substance of the professional
  conversation — background, experience, motivations, requirements, and next steps."""


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------


def stream_chat_response(
    payload: ChatRequest, db: Session, tenant_id: str
) -> Iterator[str]:
    """
    1. Yield __STATUS__ progress signals during the tool-call loop.
    2. Run agentic tool-call loop synchronously (fast DB queries).
    3. Stream the final Claude text response token by token.
    4. Emit a trailing __DATA__ chunk with structured card data.

    Stream protocol:
      "__STATUS__:Message\n"  — progress update (tool-call phase only)
      text chunks             — streamed response tokens
      "\n__DATA__\n" + JSON   — trailing structured data
    """
    messages = []
    for msg in payload.history or []:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": payload.message})

    all_candidates: list = []
    all_employers: list = []
    all_meetings: list = []
    all_job_orders: list = []

    # EP16: build tenant-scoped dispatch table for this request
    tool_dispatch = make_tool_dispatch(tenant_id)

    # Resolve the system prompt for THIS tenant, on THIS request.
    # Was a module-level constant hardcoded to accounting/finance — see
    # build_system_prompt() for why it had to become a function.
    system_prompt = build_system_prompt(get_branding(db, tenant_id))

    # Emit immediately so the client gets feedback before any Claude call
    yield "__STATUS__:Thinking...\n"

    # ── Agentic tool-call loop (non-streaming) ─────────────────────────────
    max_iterations = 5
    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append(
                {
                    "role": "assistant",
                    "content": [block.model_dump() for block in response.content],
                }
            )

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                # ── Emit progress signal before running the tool ───────────
                status_msg = TOOL_STATUS_MESSAGES.get(tool_name, "Searching...")
                yield f"__STATUS__:{status_msg}\n"

                logger.info(
                    f"Chat tool call: {tool_name}({tool_input}) tenant={tenant_id}"
                )

                if tool_name not in tool_dispatch:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = tool_dispatch[tool_name](db, tool_input)
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        result = {"error": str(e)}

                if "candidates" in result:
                    all_candidates.extend(result["candidates"])
                if "employers" in result:
                    all_employers.extend(result["employers"])
                if "meetings" in result:
                    all_meetings.extend(result["meetings"])
                if "job_orders" in result:
                    all_job_orders.extend(result["job_orders"])

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(result),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        else:
            yield "I encountered an unexpected issue. Please try again."
            return

    else:
        yield "I reached the maximum number of steps. Please ask a simpler question."
        return

    # Signal that we're now generating the written response
    yield "__STATUS__:Generating response...\n"

    # ── Stream the final answer token by token ─────────────────────────────
    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text_chunk in stream.text_stream:
                yield text_chunk
    except anthropic.APIStatusError as e:
        logger.error(f"Anthropic streaming error: {e}")
        yield "\n\nI encountered an error generating a response. Please try again."
        return
    except Exception as e:
        logger.error(f"Unexpected streaming error: {e}")
        yield "\n\nSomething went wrong. Please try again."
        return

    # ── Deduplicate structured results ─────────────────────────────────────
    def dedup(items):
        seen, out = set(), []
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                out.append(item)
        return out

    def extract_ids(items):
        seen, out = set(), []
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                out.append(item["id"])
        return out or None

    structured = {
        "candidates": extract_ids(all_candidates),
        "employers": extract_ids(all_employers),
        "meetings": dedup(all_meetings)
        or None,  # meetings stay as full objects — no modal to link to
        "job_orders": extract_ids(all_job_orders),
    }

    # ── Trailing data chunk ────────────────────────────────────────────────
    yield "\n__DATA__\n" + json.dumps(structured)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("")
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    tenant_id: str = Depends(get_current_admin_tenant),
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    return StreamingResponse(
        stream_chat_response(payload, db, tenant_id),
        media_type="text/plain",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
