# app/api/db_explorer.py
# Register in main.py:
#   from app.api.db_explorer import router as db_explorer_router
#   app.include_router(db_explorer_router)

# app/api/db_explorer.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_admin_user

router = APIRouter(prefix="/admin", tags=["db-explorer"])

TABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "id",
        "booking_type",
        "status",
        "employer_name",
        "employer_email",
        "company_name",
        "date",
        "time_slot",
        "phone",
        "notes",
        "meeting_url",
        "calendar_event_id",
        "employer_profile_id",
        "candidate_id",
        "call_outcome",
        "call_notes",
        "meeting_summary",
        "meeting_next_steps",
        "meeting_keywords",
        "meeting_transcript",
        "reminded_at",
        "embedded_at",
        "created_at",
        "updated_at",
    ],
    "candidates": [
        "id",
        "tenant_id",
        "name",
        "email",
        "phone",
        "linkedin_url",
        "current_title",
        "current_company",
        "location",
        "ai_career_level",
        "ai_years_experience",
        "ai_certifications",
        "ai_summary",
        "ai_experience",
        "ai_education",
        "ai_outreach_message",
        "notes",
        "embedded_at",
        "ai_parsed_at",
        "created_at",
        "updated_at",
    ],
    "employer_profiles": [
        "id",
        "company_name",
        "website_url",
        "primary_contact_email",
        "phone",
        "ai_industry",
        "ai_company_size",
        "ai_company_overview",
        "ai_hiring_needs",
        "ai_talking_points",
        "ai_red_flags",
        "recruiter_notes",
        "relationship_status",
        "tenant_id",
        "embedded_at",
        "created_at",
        "updated_at",
    ],
    "job_orders": [
        "id",
        "tenant_id",
        "employer_profile_id",
        "title",
        "location",
        "salary_min",
        "salary_max",
        "requirements",
        "notes",
        "status",
        "embedded_at",
        "filled_at",
        "created_at",
        "updated_at",
    ],
    "chat_sessions": [
        "id",
        "user_id",
        "title",
        "created_at",
        "updated_at",
    ],
    "chat_messages": [
        "id",
        "session_id",
        "role",
        "content",
        "structured_data",
        "created_at",
    ],
    "users": [
        "id",
        "email",
        "full_name",
        "user_type",
        "oauth_provider",
        "is_active",
        "is_superuser",
        "tenant_id",
        "created_at",
        "updated_at",
    ],
    "waitlist": [
        "id",
        "email",
        "intent",
        "source",
        "created_at",
    ],
    "contacts": [
        "id",
        "name",
        "email",
        "message",
    ],
}

SEARCHABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "employer_name",
        "employer_email",
        "company_name",
        "status",
        "booking_type",
        "call_outcome",
    ],
    "candidates": [
        "name",
        "email",
        "current_title",
        "current_company",
        "location",
        "ai_career_level",
    ],
    "employer_profiles": [
        "company_name",
        "primary_contact_email",
        "ai_industry",
        "relationship_status",
    ],
    "job_orders": ["title", "location", "status"],
    "chat_sessions": ["title"],
    "chat_messages": ["content", "role"],
    "users": ["email", "full_name", "user_type"],
    "waitlist": ["email", "intent"],
    "contacts": ["name", "email"],
}


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
