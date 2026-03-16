# app/api/chat.py
"""
RYZE.ai Chat — Phase 3 (Streaming + Progress Signals)

Agentic loop runs tool calls synchronously (fast DB queries),
then streams the final Claude text response token-by-token.
A trailing JSON chunk carries structured data (candidate/meeting cards).

Stream protocol (newline-delimited):
  - Status chunks:  "__STATUS__:Message\n" — emitted during tool-call phase
  - Text chunks:    plain text fragments streamed as they arrive
  - Final chunk:    "\n__DATA__\n" + JSON with candidates/employers/meetings/job_orders
"""
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
}


# ---------------------------------------------------------------------------
# Tool definitions
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
    embedding = generate_embedding(query)
    if not embedding:
        return []

    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    sql = text(
        f"""
        SELECT id, (embedding <=> '{vector_str}'::vector) AS distance
        FROM {table_name}
        WHERE embedding IS NOT NULL
        ORDER BY distance
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"limit": limit}).fetchall()
    return rows


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
                "company_name": j.company_name,
                "location": j.location,
                "salary_range": j.salary_range,
                "score": round(max(0.0, 1.0 - float(distances[jid])), 4),
            }
        )

    return {"job_orders": results, "count": len(results)}


def tool_get_todays_meetings(db: Session) -> dict:
    today = date.today()
    bookings = (
        db.query(Booking)
        .filter(Booking.date == today.isoformat())
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
                "date": b.date,
                "time_slot": b.time_slot,
                "status": b.status,
                "meeting_url": b.meeting_url,
                "meeting_type": b.meeting_type,
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_meetings_by_date(
    db: Session, start_date: str, end_date: Optional[str] = None
) -> dict:
    end = end_date or start_date
    bookings = (
        db.query(Booking)
        .filter(Booking.date >= start_date, Booking.date <= end)
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
                "date": b.date,
                "time_slot": b.time_slot,
                "status": b.status,
                "meeting_url": b.meeting_url,
                "meeting_type": b.meeting_type,
            }
        )

    return {"meetings": results, "count": len(results)}


def tool_get_candidate_by_name(db: Session, name: str) -> dict:
    candidates = (
        db.query(Candidate).filter(Candidate.name.ilike(f"%{name}%")).limit(5).all()
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
                "score": None,
            }
        )

    return {"candidates": results, "count": len(results)}


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

SYSTEM_PROMPT = f"""You are RYZE Intelligence — the AI assistant for RYZE.ai, a specialized accounting and finance recruiting firm based in Boston.

You have direct access to the recruiter's live database.

Today's date is {date.today().strftime("%B %d, %Y")}.

RESPONSE STYLE — follow these rules strictly:
- Be concise. Most answers should be 2–5 sentences or a short list. Never pad.
- No markdown headers. No bold labels. Plain prose or simple lists only.
- Lead with the answer immediately. No preamble like "Great question" or "Based on your database..."
- For candidate lists: name, title, one key detail per line. That's it.
- For meetings: name, company, time. One line each.
- If you don't have data, say so in one sentence and stop.
- Never repeat information already stated in the same response."""


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------


def stream_chat_response(payload: ChatRequest, db: Session) -> Iterator[str]:
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

    # Emit immediately so the client gets feedback before any Claude call
    yield "__STATUS__:Thinking...\n"

    # ── Agentic tool-call loop (non-streaming) ─────────────────────────────
    max_iterations = 5
    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
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

                logger.info(f"Chat tool call: {tool_name}({tool_input})")

                if tool_name not in TOOL_DISPATCH:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = TOOL_DISPATCH[tool_name](db, tool_input)
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
            model="claude-opus-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
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

    structured = {
        "candidates": dedup(all_candidates) or None,
        "employers": dedup(all_employers) or None,
        "meetings": dedup(all_meetings) or None,
        "job_orders": dedup(all_job_orders) or None,
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
    _: User = Depends(require_admin),
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    return StreamingResponse(
        stream_chat_response(payload, db),
        media_type="text/plain",
        headers={
            "X-Accel-Buffering": "no",  # tell nginx not to buffer the stream
            "Cache-Control": "no-cache",
        },
    )
