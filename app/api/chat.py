# app/api/chat.py
"""
RYZE.ai Chat — Phase 3

Conversational AI interface backed by Claude with tool_use.
Claude decides which tools to call based on the recruiter's question,
retrieves live data from the database, and synthesizes a natural language answer.
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.bookings import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking
from app.models.candidate import Candidate
from app.models.employer_profile import EmployerProfile
from app.models.job_order import JobOrder
from app.models.user import User
from app.services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []


class ChatResponse(BaseModel):
    response: str
    candidates: Optional[list] = None
    employers: Optional[list] = None
    meetings: Optional[list] = None
    job_orders: Optional[list] = None


# ---------------------------------------------------------------------------
# Tool definitions — what Claude can call
# ---------------------------------------------------------------------------

TOOLS = [
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
]


# ---------------------------------------------------------------------------
# Tool execution functions
# ---------------------------------------------------------------------------


def _vector_search(db: Session, table_name: str, query: str, limit: int) -> list:
    """Run cosine similarity search using raw SQL."""
    vector = generate_embedding(query)
    if not vector:
        return []
    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
    sql = text(
        f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM {table_name}
        WHERE embedding IS NOT NULL
        ORDER BY distance
        LIMIT :limit
    """
    )
    return db.execute(sql, {"limit": limit}).fetchall()


def tool_search_candidates(db: Session, query: str, limit: int = 5) -> dict:
    rows = _vector_search(db, "candidates", query, limit)
    if not rows:
        return {"candidates": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    candidates = db.query(Candidate).filter(Candidate.id.in_(ids)).all()
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
                "ai_skills": c.ai_skills or [],
                "score": round(max(0.0, 1.0 - float(distances[cid])), 4),
            }
        )

    return {"candidates": results, "count": len(results)}


def tool_search_employers(db: Session, query: str, limit: int = 5) -> dict:
    rows = _vector_search(db, "employer_profiles", query, limit)
    if not rows:
        return {"employers": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    employers = db.query(EmployerProfile).filter(EmployerProfile.id.in_(ids)).all()
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
                "relationship_status": e.relationship_status,
                "score": round(max(0.0, 1.0 - float(distances[eid])), 4),
            }
        )

    return {"employers": results, "count": len(results)}


def tool_search_job_orders(db: Session, query: str, limit: int = 5) -> dict:
    rows = _vector_search(db, "job_orders", query, limit)
    if not rows:
        return {"job_orders": [], "count": 0}

    ids = [r[0] for r in rows]
    distances = {r[0]: r[1] for r in rows}
    jobs = db.query(JobOrder).filter(JobOrder.id.in_(ids)).all()
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


def _format_booking(b: Booking) -> dict:
    return {
        "id": b.id,
        "date": str(b.date),
        "time_slot": b.time_slot,
        "status": b.status,
        "employer_name": b.employer_name,
        "company_name": b.company_name,
        "booking_type": b.booking_type,
        "meeting_url": b.meeting_url,
        "meeting_summary": b.meeting_summary,
        "notes": b.notes,
    }


def tool_get_todays_meetings(db: Session) -> dict:
    today = date.today()
    bookings = (
        db.query(Booking)
        .filter(Booking.date == today)
        .order_by(Booking.time_slot)
        .all()
    )
    return {
        "date": str(today),
        "meetings": [_format_booking(b) for b in bookings],
        "count": len(bookings),
    }


def tool_get_meetings_by_date(
    db: Session, start_date: str, end_date: Optional[str] = None
) -> dict:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date) if end_date else start
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    bookings = (
        db.query(Booking)
        .filter(Booking.date >= start, Booking.date <= end)
        .order_by(Booking.date, Booking.time_slot)
        .all()
    )
    return {
        "start_date": str(start),
        "end_date": str(end),
        "meetings": [_format_booking(b) for b in bookings],
        "count": len(bookings),
    }


def tool_get_candidate_by_name(db: Session, name: str) -> dict:
    tokens = name.strip().lower().split()
    query = db.query(Candidate).filter(Candidate.tenant_id == 1)
    for token in tokens:
        query = query.filter(Candidate.name.ilike(f"%{token}%"))
    candidates = query.limit(5).all()

    if not candidates:
        return {"candidates": [], "count": 0}

    return {
        "candidates": [
            {
                "id": c.id,
                "name": c.name,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "location": c.location,
                "email": c.email,
                "phone": c.phone,
                "ai_summary": c.ai_summary,
                "ai_career_level": c.ai_career_level,
                "ai_certifications": c.ai_certifications,
                "ai_years_experience": c.ai_years_experience,
                "ai_skills": c.ai_skills or [],
                "ai_experience": c.ai_experience,
                "notes": c.notes,
            }
            for c in candidates
        ],
        "count": len(candidates),
    }


def tool_get_employer_by_name(db: Session, name: str) -> dict:
    employers = (
        db.query(EmployerProfile)
        .filter(EmployerProfile.company_name.ilike(f"%{name}%"))
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


def tool_match_candidates_to_job(db: Session, job_title: str, limit: int = 5) -> dict:
    return tool_search_candidates(db, job_title, limit)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

TOOL_DISPATCH = {
    "search_candidates": lambda db, inp: tool_search_candidates(
        db, inp["query"], inp.get("limit", 5)
    ),
    "search_employers": lambda db, inp: tool_search_employers(
        db, inp["query"], inp.get("limit", 5)
    ),
    "search_job_orders": lambda db, inp: tool_search_job_orders(
        db, inp["query"], inp.get("limit", 5)
    ),
    "get_todays_meetings": lambda db, inp: tool_get_todays_meetings(db),
    "get_meetings_by_date": lambda db, inp: tool_get_meetings_by_date(
        db, inp["start_date"], inp.get("end_date")
    ),
    "get_candidate_by_name": lambda db, inp: tool_get_candidate_by_name(
        db, inp["name"]
    ),
    "get_employer_by_name": lambda db, inp: tool_get_employer_by_name(db, inp["name"]),
    "match_candidates_to_job": lambda db, inp: tool_match_candidates_to_job(
        db, inp["job_title"], inp.get("limit", 5)
    ),
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are RYZE Intelligence — the AI assistant for RYZE.ai, a specialized accounting and finance recruiting firm based in Boston. You have direct access to the recruiter's live database of candidates, employer profiles, job orders, and meeting history.

Today's date is {date.today().strftime("%B %d, %Y")}.

Your role:
- Answer recruiting questions using real data from the database
- Help the recruiter find the right candidates for open roles
- Surface insights about employers, meetings, and pipeline
- Be concise, specific, and actionable — you're talking to a busy recruiter

When presenting candidates:
- Lead with the most relevant match
- Mention name, title, certifications, years of experience, and what makes them a fit
- Be specific — reference actual details from their profile, not generic summaries

When presenting meetings:
- Include the contact name, company, time, and status
- Mention the Zoom link if confirmed

When you don't have data:
- Say so clearly — don't invent candidates or companies
- Suggest what additional data would help

Keep responses focused and professional. Use bullet points for lists of candidates or meetings. Avoid unnecessary preamble."""


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    RYZE Intelligence chat endpoint.
    Accepts a message and conversation history, returns AI response with optional structured data.
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Build conversation history for Claude
    messages = []
    for msg in payload.history or []:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": payload.message})

    # Accumulated structured results across all tool calls
    all_candidates = []
    all_employers = []
    all_meetings = []
    all_job_orders = []

    # Agentic loop — Claude may call multiple tools
    max_iterations = 5
    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # If Claude is done (no more tool calls), extract final text response
        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            break

        # Process tool calls
        if response.stop_reason == "tool_use":
            # Add assistant's response (with tool_use blocks) to history
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                logger.info(f"Chat tool call: {tool_name}({tool_input})")

                if tool_name not in TOOL_DISPATCH:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = TOOL_DISPATCH[tool_name](db, tool_input)
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        result = {"error": str(e)}

                # Accumulate structured results for frontend cards
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

            # Add tool results to conversation
            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason
            final_text = "I encountered an unexpected issue. Please try again."
            break
    else:
        final_text = (
            "I reached the maximum number of steps. Please try a simpler question."
        )

    # Deduplicate results by ID
    seen_candidates = set()
    unique_candidates = []
    for c in all_candidates:
        if c["id"] not in seen_candidates:
            seen_candidates.add(c["id"])
            unique_candidates.append(c)

    seen_employers = set()
    unique_employers = []
    for e in all_employers:
        if e["id"] not in seen_employers:
            seen_employers.add(e["id"])
            unique_employers.append(e)

    seen_meetings = set()
    unique_meetings = []
    for m in all_meetings:
        if m["id"] not in seen_meetings:
            seen_meetings.add(m["id"])
            unique_meetings.append(m)

    seen_jobs = set()
    unique_jobs = []
    for j in all_job_orders:
        if j["id"] not in seen_jobs:
            seen_jobs.add(j["id"])
            unique_jobs.append(j)

    return ChatResponse(
        response=final_text,
        candidates=unique_candidates if unique_candidates else None,
        employers=unique_employers if unique_employers else None,
        meetings=unique_meetings if unique_meetings else None,
        job_orders=unique_jobs if unique_jobs else None,
    )
