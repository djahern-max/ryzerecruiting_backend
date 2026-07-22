# app/api/db_explorer.py
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_superuser, RYZE_TENANT

router = APIRouter(prefix="/admin", tags=["db-explorer"])

# ---------------------------------------------------------------------------
# Tables that have a tenant_id column — all queries on these tables are
# scoped to the authenticated admin's tenant, EXCEPT for the platform owner
# (RYZE's own superadmin, _is_platform_owner()), who gets an unscoped, global
# view across every table. Tables NOT in this set are either global
# (waitlist, contacts, webhook_logs) or scoped by a different key
# (chat_sessions → user_id).
# ---------------------------------------------------------------------------

TENANT_SCOPED_TABLES = {
    "candidates",
    "employer_profiles",
    "job_orders",
    "bookings",
    "users",
    "job_interests",
}

# ---------------------------------------------------------------------------
# TABLE_COLS — every visible column per table in logical display order.
# Excluded: embedding (Vector — unreadable), hashed_password (security)
# ---------------------------------------------------------------------------

TABLE_COLS: dict[str, list[str]] = {
    "bookings": [
        "id",
        "tenant_id",
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
        "email",
        "full_name",
        "user_type",
        "tenant_id",
        "is_active",
        "is_superuser",
        "invited_at",
        "invited_by",
        "first_login_at",
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
    "webhook_logs": [
        "id",
        "event",
        "meeting_id",
        "meeting_uuid",
        "booking_found",
        "result",
        "raw_payload",
        "received_at",
    ],
    "job_interests": [
        "id",
        "tenant_id",
        "job_order_id",
        "candidate_id",
        "note",
        "created_at",
    ],
    # tenants is a global, superuser-only view — no tenant_id column, so it's
    # deliberately excluded from TENANT_SCOPED_TABLES. twilio_auth_token is
    # omitted (secret stub), same principle as hashed_password/embedding above.
    # DELETE has no cascade: other tables reference tenant_id as a plain
    # string with no FK constraint, so deleting a tenants row here does NOT
    # remove or reassign its dependents — their rows silently fall back to
    # RYZE branding via get_branding()'s per-field default. Superuser beware.
    "tenants": [
        "id",
        "slug",
        "company_name",
        "status",
        "trial_starts_at",
        "trial_ends_at",
        "stripe_customer_id",
        "stripe_subscription_id",
        "from_email",
        "reply_to_email",
        "support_email",
        "admin_email",
        "signature_name",
        "twilio_account_sid",
        "twilio_from_number",
        "created_at",
        "updated_at",
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
    "webhook_logs": ["event", "meeting_id", "result", "booking_found"],
    "job_interests": ["note"],
    "tenants": ["slug", "company_name", "status", "admin_email"],
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
    "webhook_logs": [],
    "job_interests": ["note"],
    # Read-only: slug is the tenant identity (referenced by plain-string
    # tenant_id everywhere, no FK) and must never be edited here — do that
    # through a dedicated migration/tool, not this generic PATCH. status,
    # trial_*, and stripe_* are platform-owned billing/lifecycle state, not
    # branding — same boundary already drawn in TenantBrandingUpdate
    # (app/api/settings.py), which is the correct place for tenant-editable
    # fields, not the DB explorer.
    "tenants": [],
}

TABLES_WITH_UPDATED_AT = {
    "bookings",
    "candidates",
    "employer_profiles",
    "job_orders",
    "users",
    "chat_sessions",
    "tenants",
}


# ---------------------------------------------------------------------------
# Helper — resolve tenant from current user
# ---------------------------------------------------------------------------


def _tenant(user) -> str:
    return user.tenant_id or "ryze"


def _is_platform_owner(user) -> bool:
    """RYZE's own superadmin (tenant_id == 'ryze') gets a global, unscoped view
    across every table. Any other user — including a firm-level superuser, should
    one ever exist — stays scoped to their own tenant, preserving isolation."""
    return (user.tenant_id or RYZE_TENANT) == RYZE_TENANT


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/db/explorer/tables")
async def list_tables(current_user=Depends(get_current_superuser)):
    return {"tables": list(TABLE_COLS.keys())}


@router.get("/db/counts")
async def get_all_counts(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superuser),
):
    """Row count for every table — scoped to tenant where applicable, except
    for the platform owner (_is_platform_owner()), who sees unscoped global
    counts across every table."""
    tenant_id = _tenant(current_user)
    unscoped = _is_platform_owner(current_user)
    counts = {}
    for table in TABLE_COLS:
        try:
            if table in TENANT_SCOPED_TABLES and not unscoped:
                counts[table] = (
                    db.execute(
                        text(
                            f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id = :tid'
                        ),
                        {"tid": tenant_id},
                    ).scalar()
                    or 0
                )
            else:
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
    current_user=Depends(get_current_superuser),
):
    if table not in TABLE_COLS:
        raise HTTPException(
            status_code=400, detail=f"Table '{table}' is not available."
        )

    tenant_id = _tenant(current_user)
    unscoped = _is_platform_owner(current_user)
    cols = TABLE_COLS[table]
    searchable = SEARCHABLE_COLS.get(table, [])
    cols_sql = ", ".join(f'"{c}"' for c in cols)

    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    # Tenant filter — applied first so it anchors every query on scoped
    # tables, except for the platform owner, who gets an unscoped global view
    if table in TENANT_SCOPED_TABLES and not unscoped:
        conditions.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id

    if search and search.strip() and searchable:
        sc = " OR ".join(f'"{c}"::text ILIKE :search' for c in searchable)
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
    current_user=Depends(get_current_superuser),
):
    """Patch editable fields on a record. Only EDITABLE_COLS are accepted.
    On tenant-scoped tables the WHERE clause includes tenant_id so cross-tenant
    writes silently 404 — same pattern as the REST endpoints. Exception: the
    platform owner (_is_platform_owner()) edits unscoped, by id alone."""
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

    # Tenant-scoped tables require a matching tenant_id in the WHERE clause,
    # except for the platform owner, who edits unscoped by id alone
    if table in TENANT_SCOPED_TABLES and not _is_platform_owner(current_user):
        tenant_id = _tenant(current_user)
        result = db.execute(
            text(
                f'UPDATE "{table}" SET {", ".join(set_parts)} '
                f"WHERE id = :record_id AND tenant_id = :tenant_id"
            ),
            {**updates, "record_id": record_id, "tenant_id": tenant_id},
        )
    else:
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
    current_user=Depends(get_current_superuser),
):
    """Hard delete a record by ID. On tenant-scoped tables the WHERE clause
    includes tenant_id — cross-tenant deletes return 404. Exception: the
    platform owner (_is_platform_owner()) deletes unscoped, by id alone."""
    if table not in TABLE_COLS:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not found.")

    if table in TENANT_SCOPED_TABLES and not _is_platform_owner(current_user):
        tenant_id = _tenant(current_user)
        result = db.execute(
            text(f'DELETE FROM "{table}" WHERE id = :id AND tenant_id = :tenant_id'),
            {"id": record_id, "tenant_id": tenant_id},
        )
    else:
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
    current_user=Depends(get_current_superuser),
):
    """Export the current filtered view as a CSV file download.
    Tenant-scoped tables are filtered to the requesting admin's tenant,
    except for the platform owner (_is_platform_owner()), who exports
    unscoped, global data."""
    if table not in TABLE_COLS:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not available.")

    tenant_id = _tenant(current_user)
    unscoped = _is_platform_owner(current_user)
    cols = TABLE_COLS[table]
    searchable = SEARCHABLE_COLS.get(table, [])
    cols_sql = ", ".join(f'"{c}"' for c in cols)

    conditions = []
    params: dict = {}

    if table in TENANT_SCOPED_TABLES and not unscoped:
        conditions.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id

    if search and search.strip() and searchable:
        sc = " OR ".join(f'"{c}"::text ILIKE :search' for c in searchable)
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
