"""rename_employer_name_to_contact_name

Revision ID: 2f802617893b
Revises: c320b5d1795c
Create Date: 2026-03-19 05:02:53.900710

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2f802617893b"
down_revision: Union[str, None] = "c320b5d1795c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("bookings", "employer_name", new_column_name="contact_name")


def downgrade() -> None:
    op.alter_column("bookings", "contact_name", new_column_name="employer_name")
