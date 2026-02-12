"""Add user_type and OAuth fields

Revision ID: 945f8677dbb0
Revises: 8f88f9278b11
Create Date: 2026-02-12 05:37:31.227956

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "945f8677dbb0"
down_revision: Union[str, None] = "8f88f9278b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Create the enum type FIRST
    usertype_enum = sa.Enum("EMPLOYER", "CANDIDATE", name="usertype")
    usertype_enum.create(op.get_bind(), checkfirst=True)

    # Step 2: Add columns (user_type as nullable initially)
    op.add_column("users", sa.Column("user_type", usertype_enum, nullable=True))
    op.add_column("users", sa.Column("oauth_provider", sa.String(), nullable=True))
    op.add_column("users", sa.Column("oauth_provider_id", sa.String(), nullable=True))

    # Step 3: Set default user_type for existing users
    op.execute("UPDATE users SET user_type = 'CANDIDATE' WHERE user_type IS NULL")

    # Step 4: Make user_type non-nullable now that all rows have values
    op.alter_column("users", "user_type", nullable=False)

    # Step 5: Make hashed_password nullable (for future OAuth users)
    op.alter_column("users", "hashed_password", nullable=True)


def downgrade() -> None:
    # Reverse the changes
    op.alter_column("users", "hashed_password", nullable=False)
    op.drop_column("users", "oauth_provider_id")
    op.drop_column("users", "oauth_provider")
    op.drop_column("users", "user_type")

    # Drop the enum type
    usertype_enum = sa.Enum("EMPLOYER", "CANDIDATE", name="usertype")
    usertype_enum.drop(op.get_bind(), checkfirst=True)
