"""add risks composite referential identity (P2.8A6P)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('risks') as batch_op:
        batch_op.create_unique_constraint(
            'uq_risks_tenant_case_id',
            ['tenant_id', 'case_id', 'id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('risks') as batch_op:
        batch_op.drop_constraint(
            'uq_risks_tenant_case_id',
            type_='unique',
        )
