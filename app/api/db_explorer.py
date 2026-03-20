# app/api/db_explorer.py
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_admin_user

router = APIRouter(prefix="/admin", tags=["db-explorer"])

# ---------------------------------------------------------------------------
# TABLE_COLS — every visible column per table in logical display order.
# Excluded: embedding (Vector — unreadable), hashed_password (security)
# ---------------------------------------------------------------------------

TABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "id",
        "booking_type",
        "status",
        "employer_id",
        "employer_name",
        "employer_email",
        "company_name",
        "website_url",
        "phone",
        "employer_profile_id",
        "candidate_id",
        "date",
        "time_slot",
        "notes",
        "response_token",
        "meeting_url",
        "calendar_event_id",
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
        "ai_skills",
        "ai_summary",
        "ai_experience",
        "ai_education",
        "ai_outreach_message",
        "linkedin_raw_text",
        "notes",
        "ai_parsed_at",
        "embedded_at",
        "created_at",
        "updated_at",
    ],
    "employer_profiles": [
        "id",
        "tenant_id",
        "user_id",
        "company_name",
        "website_url",
        "primary_contact_email",
        "phone",
        "relationship_status",
        "ai_industry",
        "ai_company_size",
        "ai_company_overview",
        "ai_hiring_needs",
        "ai_talking_points",
        "ai_red_flags",
        "ai_brief_raw",
        "ai_brief_updated_at",
        "recruiter_notes",
        "raw_text",
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
        "raw_text",
        "status",
        "filled_at",
        "embedded_at",
        "created_at",
        "updated_at",
    ],
    "users": [
        "id",
        "tenant_id",
        "email",
        "full_name",
        "user_type",
        "oauth_provider",
        "oauth_provider_id",
        "avatar_url",
        "is_active",
        "is_superuser",
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
    "job_orders": ["title", "location", "status"],
    "chat_sessions": ["title"],
    "chat_messages": ["content", "role"],
    "users": ["email", "full_name", "user_type", "oauth_provider", "tenant_id"],
    "waitlist": ["email", "intent", "source"],
    "contacts": ["name", "email"],
}

# Fields editable via PATCH — never includes id, timestamps, embedding, hashed_password
EDITABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "status",
        "call_outcome",
        "call_notes",
        "notes",
        "company_name",
        "website_url",
        "phone",
        "date",
        "time_slot",
        "meeting_summary",
        "meeting_next_steps",
        "meeting_keywords",
    ],
    "candidates": [
        "name",
        "email",
        "phone",
        "linkedin_url",
        "current_title",
        "current_company",
        "location",
        "notes",
        "ai_career_level",
        "ai_years_experience",
        "ai_certifications",
        "ai_summary",
        "ai_experience",
        "ai_education",
        "ai_outreach_message",
    ],
    "employer_profiles": [
        "company_name",
        "website_url",
        "primary_contact_email",
        "phone",
        "relationship_status",
        "recruiter_notes",
        "ai_industry",
        "ai_company_size",
        "ai_company_overview",
        "ai_hiring_needs",
        "ai_talking_points",
        "ai_red_flags",
    ],
    "job_orders": [
        "title",
        "location",
        "salary_min",
        "salary_max",
        "requirements",
        "notes",
        "status",
    ],
    "users": ["full_name", "is_active"],
    "waitlist": ["intent"],
    "chat_sessions": [],
    "chat_messages": [],
    "contacts": [],
}

TABLES_WITH_UPDATED_AT = {
    "bookings",
    "candidates",
    "employer_profiles",
    "job_orders",
    "users",
    "chat_sessions",
}


@router.get("/db/explorer/tables")
async def list_tables(current_user=Depends(get_current_admin_user)):
    return {"tables": list(TABLE_COLS.keys())}


@router.get("/db/counts")
async def get_all_counts(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Row count for every table — drives sidebar badges."""
    counts = {}
    for table in TABLE_COLS:
        try:
            counts[table] = (
                db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
            )
        except Exception:
            counts[table] = 0
    return counts


@router.get("/db/explorer")
async def browse_table(
    table: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=None),
    sort_col: str = Query(default=None),
    sort_dir: str = Query(default="desc"),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None),
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

    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if search and search.strip() and searchable:
        sc = " OR ".join(f'"{c}" ILIKE :search' for c in searchable)
        conditions.append(f"({sc})")
        params["search"] = f"%{search.strip()}%"

    if date_from and "created_at" in cols:
        conditions.append('"created_at" >= :date_from')
        params["date_from"] = date_from
    if date_to and "created_at" in cols:
        conditions.append('"created_at" <= :date_to')
        params["date_to"] = date_to + " 23:59:59"

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Validate sort_col against whitelist to prevent injection
    if sort_col and sort_col in cols:
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order_clause = f'ORDER BY "{sort_col}" {direction} NULLS LAST'
    else:
        order_clause = "ORDER BY id DESC"

    total = (
        db.execute(
            text(f'SELECT COUNT(*) FROM "{table}" {where_clause}'), params
        ).scalar()
        or 0
    )

    rows = (
        db.execute(
            text(
                f'SELECT {cols_sql} FROM "{table}" {where_clause} {order_clause} LIMIT :limit OFFSET :offset'
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


@router.patch("/db/records/{table}/{record_id}")
async def update_record(
    table: str,
    record_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Patch editable fields on a record. Only EDITABLE_COLS are accepted."""
    if table not in EDITABLE_COLS:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not editable.")

    allowed = set(EDITABLE_COLS[table])
    updates = {k: v for k, v in payload.items() if k in allowed}

    if not updates:
        raise HTTPException(
            status_code=400, detail="No valid editable fields provided."
        )

    set_parts = [f'"{k}" = :{k}' for k in updates]
    if table in TABLES_WITH_UPDATED_AT:
        set_parts.append("updated_at = NOW()")

    result = db.execute(
        text(f'UPDATE "{table}" SET {", ".join(set_parts)} WHERE id = :record_id'),
        {**updates, "record_id": record_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Record not found.")

    return {"status": "ok", "updated": record_id}


@router.delete("/db/records/{table}/{record_id}")
async def delete_record(
    table: str,
    record_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Hard delete a record by ID. Irreversible."""
    if table not in TABLE_COLS:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not found.")

    result = db.execute(
        text(f'DELETE FROM "{table}" WHERE id = :id'),
        {"id": record_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Record not found.")

    return {"status": "ok", "deleted": record_id}


@router.get("/db/export")
async def export_table_csv(
    table: str = Query(...),
    search: str = Query(default=None),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Export the current filtered view as a CSV file download."""
    if table not in TABLE_COLS:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not available.")

    cols = TABLE_COLS[table]
    searchable = SEARCHABLE_COLS.get(table, [])
    cols_sql = ", ".join(f'"{c}"' for c in cols)

    conditions = []
    params: dict = {}

    if search and search.strip() and searchable:
        sc = " OR ".join(f'"{c}" ILIKE :search' for c in searchable)
        conditions.append(f"({sc})")
        params["search"] = f"%{search.strip()}%"

    if date_from and "created_at" in cols:
        conditions.append('"created_at" >= :date_from')
        params["date_from"] = date_from
    if date_to and "created_at" in cols:
        conditions.append('"created_at" <= :date_to')
        params["date_to"] = date_to + " 23:59:59"

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = (
        db.execute(
            text(f'SELECT {cols_sql} FROM "{table}" {where_clause} ORDER BY id DESC'),
            params,
        )
        .mappings()
        .all()
    )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {k: (str(v) if v is not None else "") for k, v in dict(row).items()}
        )

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )
