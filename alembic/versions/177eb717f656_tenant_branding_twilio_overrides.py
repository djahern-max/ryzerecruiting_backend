"""tenant branding + twilio overrides

Revision ID: 177eb717f656
Revises: e00a9314318b
Create Date: 2026-06-24 19:39:04.224714

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "177eb717f656"
down_revision: Union[str, None] = "e00a9314318b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants", sa.Column("from_email", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("reply_to_email", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("support_email", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("signature_name", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("twilio_account_sid", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("twilio_auth_token", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("twilio_from_number", sa.String(length=30), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tenants", "twilio_from_number")
    op.drop_column("tenants", "twilio_auth_token")
    op.drop_column("tenants", "twilio_account_sid")
    op.drop_column("tenants", "signature_name")
    op.drop_column("tenants", "support_email")
    op.drop_column("tenants", "reply_to_email")
    op.drop_column("tenants", "from_email")
