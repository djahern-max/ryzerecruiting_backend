"""Add admin to usertype enum and migrate superuser records

Revision ID: a1b2c3d4e5f6
Revises: 8492ef5185b3
Create Date: 2026-02-25 12:00:00.000000

IMPORTANT: PostgreSQL does not allow ALTER TYPE ... ADD VALUE inside a transaction.
This migration commits the current transaction before adding the enum value,
then reopens one for the data update. This is safe — Alembic will still track
the migration as applied.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6f53ed7d87c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Commit the current transaction — required before ALTER TYPE ADD VALUE in Postgres
    op.execute("COMMIT")

    # Step 2: Add 'admin' to the existing usertype enum (IF NOT EXISTS is safe to re-run)
    op.execute("ALTER TYPE usertype ADD VALUE IF NOT EXISTS 'admin'")

    # Step 3: Begin a new transaction for the data update
    op.execute("BEGIN")

    # Step 4: Set user_type = 'admin' for all superusers
    op.execute("UPDATE users SET user_type = 'admin' WHERE is_superuser = TRUE")


def downgrade() -> None:
    # Revert admin users back to 'employer' before removing the value.
    # Note: PostgreSQL does not support DROP VALUE from an enum.
    # A full enum recreation would be required for a true downgrade.
    # For safety, we just reassign admin users back to employer.
    op.execute("UPDATE users SET user_type = 'employer' WHERE user_type = 'admin'")

    # If you need to fully remove 'admin' from the enum, you would need to:
    # 1. Rename the old enum
    # 2. Create a new enum without 'admin'
    # 3. Alter the column to use the new enum
    # 4. Drop the old enum
    # This is rarely necessary and risky in production — consult a DBA if needed.
