"""add meeting_url to bookings

Revision ID: f64b0fe96265
Revises: a1b2c3d4e5f6
Create Date: 2026-02-25 15:02:14.626972

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f64b0fe96265"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("meeting_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "meeting_url")
