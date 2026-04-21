"""add_user_id_to_candidates

Revision ID: 957289612b32
Revises: 8bad52f7eb0f
Create Date: 2026-04-21 04:22:31.215880

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "957289612b32"
down_revision: Union[str, None] = "8bad52f7eb0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_candidates_user_id"), "candidates", ["user_id"], unique=False
    )
    op.create_foreign_key(
        "fk_candidates_user_id",
        "candidates",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_candidates_user_id", "candidates", type_="foreignkey")
    op.drop_index(op.f("ix_candidates_user_id"), table_name="candidates")
    op.drop_column("candidates", "user_id")
