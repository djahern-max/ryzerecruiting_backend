"""tenant_id not null on five tables, tenants.billing_exempt

Tenant restructure, part 1 of 3 (schema only).

1. Backfill tenant_id = 'ryze' where NULL on candidates, bookings,
   employer_profiles, job_orders, job_interests. Zero such rows exist locally;
   on a restored production dump any NULL rows are historically RYZE
   Recruiting's data, so 'ryze' is the correct value (decided 2026-11-05).
2. Set tenant_id NOT NULL on those five tables.
3. Add tenants.billing_exempt BOOLEAN NOT NULL DEFAULT false. Replaces the
   slug == 'ryze' billing/usage exemption in part 2.

users.tenant_id stays nullable until the signup resolver has an explicit
answer for unplaced users (part 3).

Revision ID: f807a49989a8
Revises: 4083c0d3ba12
Create Date: 2026-11-05 04:00:08.880364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f807a49989a8'
down_revision: Union[str, None] = '4083c0d3ba12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HOUSE_TENANT = "ryze"

# Order matters only for readability; there are no FK dependencies on tenant_id.
TENANT_TABLES = (
    "candidates",
    "bookings",
    "employer_profiles",
    "job_orders",
    "job_interests",
)


def upgrade() -> None:
    # 1 + 2. Backfill, then tighten — one table at a time so a failure points
    # at the table that still has NULLs.
    for table in TENANT_TABLES:
        op.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :t WHERE tenant_id IS NULL")
            .bindparams(t=HOUSE_TENANT)
        )
        op.alter_column(
            table,
            "tenant_id",
            existing_type=sa.VARCHAR(length=100),
            nullable=False,
        )

    # 3. Platform/house tenants are exempt from billing and AI-budget checks.
    op.add_column(
        "tenants",
        sa.Column(
            "billing_exempt",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "billing_exempt")

    # Relax the constraints. The backfilled 'ryze' values are left in place —
    # they are indistinguishable from rows that always had tenant_id = 'ryze'.
    for table in reversed(TENANT_TABLES):
        op.alter_column(
            table,
            "tenant_id",
            existing_type=sa.VARCHAR(length=100),
            nullable=True,
        )
