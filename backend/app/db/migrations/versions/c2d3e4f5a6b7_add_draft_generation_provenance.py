"""add draft generation run provenance (P2.9B)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('draft_paragraphs', sa.Column(
        'generation_run_id', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('draft_paragraphs', sa.Column(
        'generation_input_fingerprint', sa.String(length=64), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('draft_paragraphs', 'generation_input_fingerprint')
    op.drop_column('draft_paragraphs', 'generation_run_id')
