"""add_candidate_id_to_bookings

Revision ID: b62cb0e4c288
Revises: 2f802617893b
Create Date: 2026-03-19 05:18:38.425564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b62cb0e4c288'
down_revision: Union[str, None] = '2f802617893b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings',
        sa.Column('candidate_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_bookings_candidate_id',
        'bookings', 'candidates',
        ['candidate_id'], ['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    op.drop_constraint('fk_bookings_candidate_id', 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'candidate_id')
