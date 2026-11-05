"""users.tenant_id NOT NULL — no unplaced users

Tenant restructure, part 3 of 3.

Since part 3 the signup resolver refuses any Candidate / Employer that no
firm (or more than one firm) already has on file, firms get their tenant from
/signup-firm or /admin/invite-firm, and superadmins from
scripts/create_superadmin.py --tenant. Every user therefore has a tenant and
the column can say so.

1. Backfill: UPDATE users SET tenant_id = 'green_path_recruiting'
   WHERE tenant_id IS NULL. Zero such rows locally; the backfill is for a
   restored dump, where any NULL rows predate explicit tenant stamping and are
   historically Dane's firm's accounts (same reasoning as f807a49989a8).
2. ALTER COLUMN tenant_id SET NOT NULL.

Downgrade relaxes the constraint only. The backfilled rows cannot be told
apart from rows that were already in green_path_recruiting, so it does not
try to restore NULLs — downgrade is for round-trip testing.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-05 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKFILL_SLUG = "green_path_recruiting"


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE users SET tenant_id = :slug WHERE tenant_id IS NULL").bindparams(
            slug=BACKFILL_SLUG
        )
    )
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )
