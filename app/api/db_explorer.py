# app/api/db_explorer.py
# Register in main.py:
#   from app.api.db_explorer import router as db_explorer_router
#   app.include_router(db_explorer_router)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_admin_user

router = APIRouter(prefix="/admin", tags=["db-explorer"])

# ---------------------------------------------------------------------------
# TABLE_COLS — every visible column per table, in logical display order.
#
# Intentionally excluded columns (never shown):
#   - embedding      (Vector(1536) — unreadable noise)
#   - hashed_password (security — never expose)
#
# Keep this in sync with your models as the schema grows.
# ---------------------------------------------------------------------------

TABLE_COLS: dict[str, list[str]] = {
    # ── bookings ────────────────────────────────────────────────────────────
    # Core booking flow: identity → scheduling → status → meeting → AI intel
    "bookings": [
        # Identity
        "id",
        "booking_type",
        "status",
        # Employer / contact
        "employer_id",
        "employer_name",
        "employer_email",
        "company_name",
        "website_url",
        "phone",
        # Linked records
        "employer_profile_id",
        "candidate_id",
        # Scheduling
        "date",
        "time_slot",
        "notes",
        # Outbound invite token
        "response_token",
        # Meeting & calendar
        "meeting_url",
        "calendar_event_id",
        # Post-call intelligence
        "call_outcome",
        "call_notes",
        "meeting_summary",
        "meeting_next_steps",
        "meeting_keywords",
        "meeting_transcript",
        # Embedding status
        "reminded_at",
        "embedded_at",
        # Timestamps
        "created_at",
        "updated_at",
    ],
    # ── candidates ──────────────────────────────────────────────────────────
    # Identity → contact → current position → AI fields → metadata
    "candidates": [
        # Identity & tenancy
        "id",
        "tenant_id",
        # Contact info
        "name",
        "email",
        "phone",
        "linkedin_url",
        # Current position
        "current_title",
        "current_company",
        "location",
        # AI-parsed profile fields
        "ai_career_level",
        "ai_years_experience",
        "ai_certifications",
        "ai_skills",
        "ai_summary",
        "ai_experience",
        "ai_education",
        "ai_outreach_message",
        # Source text
        "linkedin_raw_text",
        # Recruiter notes
        "notes",
        # Embedding & parse status
        "ai_parsed_at",
        "embedded_at",
        # Timestamps
        "created_at",
        "updated_at",
    ],
    # ── employer_profiles ───────────────────────────────────────────────────
    # Identity → contact → AI intelligence → recruiter intel → metadata
    "employer_profiles": [
        # Identity & tenancy
        "id",
        "tenant_id",
        "user_id",
        # Company identity
        "company_name",
        "website_url",
        "primary_contact_email",
        "phone",
        # Relationship
        "relationship_status",
        # AI-generated intelligence
        "ai_industry",
        "ai_company_size",
        "ai_company_overview",
        "ai_hiring_needs",
        "ai_talking_points",
        "ai_red_flags",
        "ai_brief_raw",
        "ai_brief_updated_at",
        # Recruiter notes
        "recruiter_notes",
        # Source text
        "raw_text",
        # Embedding status
        "embedded_at",
        # Timestamps
        "created_at",
        "updated_at",
    ],
    # ── job_orders ──────────────────────────────────────────────────────────
    # Identity → job details → status → source → metadata
    "job_orders": [
        # Identity & tenancy
        "id",
        "tenant_id",
        "employer_profile_id",
        # Job details
        "title",
        "location",
        "salary_min",
        "salary_max",
        "requirements",
        "notes",
        # Source text
        "raw_text",
        # Status
        "status",
        "filled_at",
        # Embedding status
        "embedded_at",
        # Timestamps
        "created_at",
        "updated_at",
    ],
    # ── users ───────────────────────────────────────────────────────────────
    # Identity → auth → roles → tenancy → timestamps
    # NOTE: hashed_password intentionally excluded
    "users": [
        "id",
        "tenant_id",
        "email",
        "full_name",
        "user_type",
        # OAuth
        "oauth_provider",
        "oauth_provider_id",
        "avatar_url",
        # Roles & status
        "is_active",
        "is_superuser",
        # Timestamps
        "created_at",
        "updated_at",
    ],
    # ── chat_sessions ───────────────────────────────────────────────────────
    "chat_sessions": [
        "id",
        "user_id",
        "title",
        "created_at",
        "updated_at",
    ],
    # ── chat_messages ───────────────────────────────────────────────────────
    "chat_messages": [
        "id",
        "session_id",
        "role",
        "content",
        "structured_data",
        "created_at",
    ],
    # ── waitlist ────────────────────────────────────────────────────────────
    "waitlist": [
        "id",
        "email",
        "intent",
        "source",
        "created_at",
    ],
    # ── contacts ────────────────────────────────────────────────────────────
    "contacts": [
        "id",
        "name",
        "email",
        "message",
    ],
}

# ---------------------------------------------------------------------------
# SEARCHABLE_COLS — columns included in ILIKE search per table.
# Only include short string columns — not Text blobs.
# ---------------------------------------------------------------------------

SEARCHABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "employer_name",
        "employer_email",
        "company_name",
        "status",
        "booking_type",
        "call_outcome",
        "website_url",
    ],
    "candidates": [
        "name",
        "email",
        "phone",
        "current_title",
        "current_company",
        "location",
        "ai_career_level",
        "ai_certifications",
        "linkedin_url",
    ],
    "employer_profiles": [
        "company_name",
        "primary_contact_email",
        "phone",
        "ai_industry",
        "relationship_status",
        "website_url",
    ],
    "job_orders": [
        "title",
        "location",
        "status",
    ],
    "chat_sessions": [
        "title",
    ],
    "chat_messages": [
        "content",
        "role",
    ],
    "users": [
        "email",
        "full_name",
        "user_type",
        "oauth_provider",
        "tenant_id",
    ],
    "waitlist": [
        "email",
        "intent",
        "source",
    ],
    "contacts": [
        "name",
        "email",
    ],
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/db/explorer/tables")
async def list_tables(current_user=Depends(get_current_admin_user)):
    return {"tables": list(TABLE_COLS.keys())}


@router.get("/db/explorer")
async def browse_table(
    table: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    if table not in TABLE_COLS:
        raise HTTPException(
            status_code=400, detail=f"Table '{table}' is not available."
        )

    cols = TABLE_COLS[table]
    searchable = SEARCHABLE_COLS.get(table, [])
    cols_sql = ", ".join(f'"{c}"' for c in cols)

    where_clause = ""
    params: dict = {"limit": limit, "offset": offset}

    if search and search.strip() and searchable:
        conditions = " OR ".join(f'"{c}" ILIKE :search' for c in searchable)
        where_clause = f"WHERE ({conditions})"
        params["search"] = f"%{search.strip()}%"

    total = (
        db.execute(
            text(f'SELECT COUNT(*) FROM "{table}" {where_clause}'), params
        ).scalar()
        or 0
    )

    rows = (
        db.execute(
            text(
                f'SELECT {cols_sql} FROM "{table}" {where_clause} '
                f"ORDER BY id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        .mappings()
        .all()
    )

    return {
        "table": table,
        "columns": cols,
        "rows": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
