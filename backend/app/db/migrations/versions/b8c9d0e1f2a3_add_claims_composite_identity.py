"""add claims composite referential identity (P2.8A4P)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('claims') as batch_op:
        batch_op.create_unique_constraint(
            'uq_claims_tenant_case_id',
            ['tenant_id', 'case_id', 'id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('claims') as batch_op:
        batch_op.drop_constraint(
            'uq_claims_tenant_case_id',
            type_='unique',
        )
