"""expand candidate ai fields

Revision ID: 1b18568e035d
Revises: a47617263d92
Create Date: 2026-03-14 15:10:55.918875

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1b18568e035d"
down_revision: Union[str, None] = "a47617263d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidates", sa.Column("ai_career_level", sa.String(), nullable=True)
    )
    op.add_column("candidates", sa.Column("ai_experience", sa.Text(), nullable=True))
    op.add_column("candidates", sa.Column("ai_education", sa.Text(), nullable=True))
    op.add_column(
        "candidates", sa.Column("ai_certifications", sa.Text(), nullable=True)
    )
    op.add_column("candidates", sa.Column("ai_skills", sa.JSON(), nullable=True))
    op.add_column(
        "candidates", sa.Column("ai_years_experience", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("candidates", "ai_years_experience")
    op.drop_column("candidates", "ai_skills")
    op.drop_column("candidates", "ai_certifications")
    op.drop_column("candidates", "ai_education")
    op.drop_column("candidates", "ai_experience")
    op.drop_column("candidates", "ai_career_level")
