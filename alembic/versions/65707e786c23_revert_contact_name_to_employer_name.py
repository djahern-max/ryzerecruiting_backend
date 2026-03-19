"""revert_contact_name_to_employer_name

Revision ID: 65707e786c23
Revises: b62cb0e4c288
Create Date: 2026-03-19 06:49:41.376359

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "65707e786c23"
down_revision: Union[str, None] = "b62cb0e4c288"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("bookings", "contact_name", new_column_name="employer_name")


def downgrade() -> None:
    op.alter_column("bookings", "employer_name", new_column_name="contact_name")
