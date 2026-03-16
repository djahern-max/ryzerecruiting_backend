"""standardize_tenant_id

Converts all tenant_id columns to String(100) with a consistent 'ryze' default.
Adds tenant_id to users and bookings tables.

- candidates.tenant_id:    Integer NOT NULL  → String(100) nullable, existing rows → 'ryze'
- job_orders.tenant_id:    Integer NOT NULL  → String(100) nullable, existing rows → 'ryze'
- employer_profiles.tenant_id: already String(100) nullable, NULL rows → 'ryze'
- users.tenant_id:         new column String(100) nullable, default 'ryze'
- bookings.tenant_id:      new column String(100) nullable, default 'ryze'

Revision ID: 0002_standardize_tenant_id
Revises: 12f3ab7a6fd0
Create Date: 2026-03-16
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_standardize_tenant_id"
down_revision: Union[str, None] = "12f3ab7a6fd0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── candidates ──────────────────────────────────────────────────────────
    # PostgreSQL cannot cast Integer → Varchar in-place, so:
    # 1. Add a new String column
    # 2. Copy data (integer 1 → 'ryze', any other value → its string repr)
    # 3. Drop the old Integer column
    # 4. Rename the new column

    op.add_column("candidates", sa.Column("tenant_id_new", sa.String(100), nullable=True))
    op.execute(
        "UPDATE candidates SET tenant_id_new = 'ryze'"
    )
    op.drop_column("candidates", "tenant_id")
    op.alter_column("candidates", "tenant_id_new", new_column_name="tenant_id")
    op.create_index("ix_candidates_tenant_id", "candidates", ["tenant_id"])

    # ── job_orders ───────────────────────────────────────────────────────────
    op.add_column("job_orders", sa.Column("tenant_id_new", sa.String(100), nullable=True))
    op.execute(
        "UPDATE job_orders SET tenant_id_new = 'ryze'"
    )
    op.drop_column("job_orders", "tenant_id")
    op.alter_column("job_orders", "tenant_id_new", new_column_name="tenant_id")
    op.create_index("ix_job_orders_tenant_id", "job_orders", ["tenant_id"])

    # ── employer_profiles ────────────────────────────────────────────────────
    # Already String(100) nullable — just back-fill NULLs
    op.execute(
        "UPDATE employer_profiles SET tenant_id = 'ryze' WHERE tenant_id IS NULL"
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("tenant_id", sa.String(100), nullable=True, server_default="ryze"),
    )
    op.execute("UPDATE users SET tenant_id = 'ryze'")
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ── bookings ─────────────────────────────────────────────────────────────
    op.add_column(
        "bookings",
        sa.Column("tenant_id", sa.String(100), nullable=True, server_default="ryze"),
    )
    op.execute("UPDATE bookings SET tenant_id = 'ryze'")
    op.create_index("ix_bookings_tenant_id", "bookings", ["tenant_id"])


def downgrade() -> None:
    # ── bookings ─────────────────────────────────────────────────────────────
    op.drop_index("ix_bookings_tenant_id", table_name="bookings")
    op.drop_column("bookings", "tenant_id")

    # ── users ────────────────────────────────────────────────────────────────
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")

    # ── employer_profiles ────────────────────────────────────────────────────
    # Leave as-is (already was String(100))

    # ── job_orders ───────────────────────────────────────────────────────────
    op.drop_index("ix_job_orders_tenant_id", table_name="job_orders")
    op.add_column("job_orders", sa.Column("tenant_id_old", sa.Integer(), nullable=True))
    op.execute("UPDATE job_orders SET tenant_id_old = 1")
    op.drop_column("job_orders", "tenant_id")
    op.alter_column("job_orders", "tenant_id_old", new_column_name="tenant_id")

    # ── candidates ───────────────────────────────────────────────────────────
    op.drop_index("ix_candidates_tenant_id", table_name="candidates")
    op.add_column("candidates", sa.Column("tenant_id_old", sa.Integer(), nullable=True))
    op.execute("UPDATE candidates SET tenant_id_old = 1")
    op.drop_column("candidates", "tenant_id")
    op.alter_column("candidates", "tenant_id_old", new_column_name="tenant_id")
