"""add case_facts composite referential identity (P2.8A3P)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('case_facts') as batch_op:
        batch_op.create_unique_constraint(
            'uq_case_facts_tenant_case_id',
            ['tenant_id', 'case_id', 'id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('case_facts') as batch_op:
        batch_op.drop_constraint(
            'uq_case_facts_tenant_case_id',
            type_='unique',
        )
