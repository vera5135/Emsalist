"""add evidence composite referential identity (P2.8A5P)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('evidence') as batch_op:
        batch_op.create_unique_constraint(
            'uq_evidence_tenant_case_id',
            ['tenant_id', 'case_id', 'id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('evidence') as batch_op:
        batch_op.drop_constraint(
            'uq_evidence_tenant_case_id',
            type_='unique',
        )
