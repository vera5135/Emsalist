"""add p2.7 hybrid search tables

Revision ID: a1b2c3d4e5f7
Revises: 6352fc55db15
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = '6352fc55db15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # -- create search_queries --
    op.create_table('search_queries',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('tenant_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('case_id', sa.String(length=32), nullable=True),
    sa.Column('query_hash', sa.String(length=64), nullable=False),
    sa.Column('safe_query_summary', sa.JSON(), nullable=False),
    sa.Column('filters_json', sa.JSON(), nullable=False),
    sa.Column('index_version', sa.String(length=32), nullable=False, server_default='0'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_search_queries_query_hash'), 'search_queries', ['query_hash'], unique=False)
    op.create_index(op.f('ix_search_queries_tenant_id'), 'search_queries', ['tenant_id'], unique=False)

    # -- create search_feedbacks --
    op.create_table('search_feedbacks',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('search_query_id', sa.String(length=32), nullable=False),
    sa.Column('result_id', sa.String(length=256), nullable=False),
    sa.Column('source_id', sa.String(length=32), nullable=False),
    sa.Column('feedback_type', sa.String(length=30), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_search_feedbacks_search_query_id'), 'search_feedbacks', ['search_query_id'], unique=False)
    op.create_index(op.f('ix_search_feedbacks_result_id'), 'search_feedbacks', ['result_id'], unique=False)

    # -- add embedding columns to source_paragraphs --
    op.add_column('source_paragraphs', sa.Column('embedding_model', sa.String(length=60), nullable=True))
    op.add_column('source_paragraphs', sa.Column('embedding_version', sa.String(length=40), nullable=True))
    op.add_column('source_paragraphs', sa.Column('embedding_dimension', sa.Integer(), nullable=True))
    op.add_column('source_paragraphs', sa.Column('embedding_vector_json', sa.Text(), nullable=True))
    op.add_column('source_paragraphs', sa.Column('embedding_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # -- drop embedding columns from source_paragraphs --
    op.drop_column('source_paragraphs', 'embedding_updated_at')
    op.drop_column('source_paragraphs', 'embedding_vector_json')
    op.drop_column('source_paragraphs', 'embedding_dimension')
    op.drop_column('source_paragraphs', 'embedding_version')
    op.drop_column('source_paragraphs', 'embedding_model')

    # -- drop search_feedbacks --
    op.drop_index(op.f('ix_search_feedbacks_result_id'), table_name='search_feedbacks')
    op.drop_index(op.f('ix_search_feedbacks_search_query_id'), table_name='search_feedbacks')
    op.drop_table('search_feedbacks')

    # -- drop search_queries --
    op.drop_index(op.f('ix_search_queries_tenant_id'), table_name='search_queries')
    op.drop_index(op.f('ix_search_queries_query_hash'), table_name='search_queries')
    op.drop_table('search_queries')
