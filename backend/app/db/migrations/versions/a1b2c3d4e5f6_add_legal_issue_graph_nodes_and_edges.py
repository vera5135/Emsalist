"""add_legal_issue_graph_nodes_and_edges

Revision ID: a1b2c3d4e5f6
Revises: e3fa017c1ae1
Create Date: 2026-07-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e3fa017c1ae1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('legal_issue_nodes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('node_type', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('source_type', sa.String(length=30), nullable=False),
        sa.Column('source_id', sa.String(length=32), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_legal_issue_nodes_tenant_case', 'legal_issue_nodes', ['tenant_id', 'case_id'], unique=False)
    op.create_index('ix_legal_issue_nodes_case_type', 'legal_issue_nodes', ['case_id', 'node_type'], unique=False)
    op.create_index('ix_legal_issue_nodes_source', 'legal_issue_nodes', ['source_type', 'source_id'], unique=False)

    op.create_table('legal_issue_edges',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('source_node_id', sa.String(length=32), nullable=False),
        sa.Column('target_node_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_legal_issue_edges_tenant_case', 'legal_issue_edges', ['tenant_id', 'case_id'], unique=False)
    op.create_index('ix_legal_issue_edges_source', 'legal_issue_edges', ['source_node_id'], unique=False)
    op.create_index('ix_legal_issue_edges_target', 'legal_issue_edges', ['target_node_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('legal_issue_edges')
    op.drop_table('legal_issue_nodes')
