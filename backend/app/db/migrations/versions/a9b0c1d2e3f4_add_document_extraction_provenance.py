"""add document extraction provider provenance

Revision ID: a9b0c1d2e3f4
Revises: 6b7c8d9e0f1a
Create Date: 2026-07-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = '6b7c8d9e0f1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_extractions', sa.Column('provider_name', sa.String(length=40), nullable=False, server_default=''))
    op.add_column('document_extractions', sa.Column('provider_model', sa.String(length=80), nullable=False, server_default=''))
    op.add_column('document_extractions', sa.Column('analysis_run_id', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('document_extractions', sa.Column('source_quote', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('document_extractions', 'source_quote')
    op.drop_column('document_extractions', 'analysis_run_id')
    op.drop_column('document_extractions', 'provider_model')
    op.drop_column('document_extractions', 'provider_name')
