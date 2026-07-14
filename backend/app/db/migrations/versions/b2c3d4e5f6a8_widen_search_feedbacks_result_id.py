"""widen search_feedbacks result_id to 512

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('search_feedbacks') as batch_op:
        batch_op.alter_column(
            'result_id',
            existing_type=sa.String(length=256),
            type_=sa.String(length=512),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('search_feedbacks') as batch_op:
        batch_op.alter_column(
            'result_id',
            existing_type=sa.String(length=512),
            type_=sa.String(length=256),
            existing_nullable=False,
        )
