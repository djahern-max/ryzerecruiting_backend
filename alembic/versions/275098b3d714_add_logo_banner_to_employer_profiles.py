"""add_logo_banner_to_employer_profiles

Revision ID: 275098b3d714
Revises: 3af477b032b5
Create Date: 2026-05-04 20:02:58.712999

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "275098b3d714"
down_revision = "3af477b032b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employer_profiles",
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "employer_profiles",
        sa.Column("banner_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employer_profiles", "banner_url")
    op.drop_column("employer_profiles", "logo_url")
