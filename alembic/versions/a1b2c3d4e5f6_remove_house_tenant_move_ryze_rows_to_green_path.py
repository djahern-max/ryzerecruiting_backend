"""remove house tenant: upsert green_path_recruiting, move ryze rows into it

Tenant restructure, part 2 of 3 (data only — no schema change).

There is no house tenant any more. Code no longer treats the slug 'ryze' as
special, a slug with no tenants row gets 403, and billing exemption comes from
tenants.billing_exempt. This migration makes the existing data consistent with
that:

1. Upsert the tenants row for slug 'green_path_recruiting' (Decision 1a,
   2026-11-05): company_name 'Green Path Recruiting', status 'active',
   billing_exempt true. The demo seed may already have created it, so an
   existing row is UPDATEd rather than duplicated.
2. Move every row stamped 'ryze' on users and the five tenant data tables
   into 'green_path_recruiting', plus any superuser with a NULL tenant_id.

Downgrade reverses the UPDATEs back to 'ryze' and leaves the tenants row in
place — deleting a tenant is never a migration's job.

Revision ID: a1b2c3d4e5f6
Revises: f807a49989a8
Create Date: 2026-11-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f807a49989a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_SLUG = "ryze"
NEW_SLUG = "green_path_recruiting"
NEW_NAME = "Green Path Recruiting"

TENANT_TABLES = (
    "candidates",
    "bookings",
    "employer_profiles",
    "job_orders",
    "job_interests",
)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Upsert the tenant row (update-if-exists so a seeded row is reused).
    conn.execute(
        sa.text(
            """
            INSERT INTO tenants (slug, company_name, status, billing_exempt)
            VALUES (:slug, :name, 'active', true)
            ON CONFLICT (slug) DO UPDATE
                SET company_name = EXCLUDED.company_name,
                    status = 'active',
                    billing_exempt = true,
                    updated_at = NOW()
            """
        ),
        {"slug": NEW_SLUG, "name": NEW_NAME},
    )

    # 2. Move users: legacy slug, plus NULL-tenant superusers.
    conn.execute(
        sa.text(
            """
            UPDATE users SET tenant_id = :new
            WHERE tenant_id = :old
               OR (tenant_id IS NULL AND is_superuser IS TRUE)
            """
        ),
        {"new": NEW_SLUG, "old": LEGACY_SLUG},
    )

    # 3. Move the five tenant data tables (NOT NULL since part 1).
    for table in TENANT_TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :new WHERE tenant_id = :old"),
            {"new": NEW_SLUG, "old": LEGACY_SLUG},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse the UPDATEs. Rows that were genuinely green_path_recruiting
    # before this migration cannot be told apart from moved ones; downgrade
    # is for round-trip testing, not for separating the two.
    for table in TENANT_TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :old WHERE tenant_id = :new"),
            {"new": NEW_SLUG, "old": LEGACY_SLUG},
        )
    conn.execute(
        sa.text("UPDATE users SET tenant_id = :old WHERE tenant_id = :new"),
        {"new": NEW_SLUG, "old": LEGACY_SLUG},
    )
    # The tenants row is intentionally left in place.
