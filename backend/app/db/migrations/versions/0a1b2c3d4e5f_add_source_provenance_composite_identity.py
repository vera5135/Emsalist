"""add source provenance composite referential identity (P2.8A7P)

Revision ID: 0a1b2c3d4e5f
Revises: f2a3b4c5d6e7
Create Date: 2026-07-15 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('source_versions') as batch_op:
        batch_op.create_unique_constraint(
            'uq_source_versions_record_id',
            ['source_record_id', 'id'],
        )
    with op.batch_alter_table('source_paragraphs') as batch_op:
        batch_op.create_unique_constraint(
            'uq_source_paragraphs_version_id',
            ['source_version_id', 'id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('source_paragraphs') as batch_op:
        batch_op.drop_constraint(
            'uq_source_paragraphs_version_id',
            type_='unique',
        )
    with op.batch_alter_table('source_versions') as batch_op:
        batch_op.drop_constraint(
            'uq_source_versions_record_id',
            type_='unique',
        )
