"""add_invite_tracking_to_users

Revision ID: e00a9314318b
Revises: 275098b3d714
Create Date: 2026-05-29 15:46:02.786552

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e00a9314318b"
down_revision: Union[str, None] = "275098b3d714"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("invited_by", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("first_login_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "invited_at")
    op.drop_column("users", "invited_by")
    op.drop_column("users", "first_login_at")
