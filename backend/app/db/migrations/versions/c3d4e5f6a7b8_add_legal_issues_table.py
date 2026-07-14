"""add canonical legal_issues table (P2.8A1)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a8
Create Date: 2026-07-14 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGAL_ISSUE_STATUSES = (
    'accepted', 'disputed', 'failed', 'needs_review',
    'proposed', 'satisfied', 'unsupported',
)


def upgrade() -> None:
    op.create_table(
        'legal_issues',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('parent_issue_id', sa.String(length=32), nullable=True),
        sa.Column('issue_code', sa.String(length=60), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_issues_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_issues_case'),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _LEGAL_ISSUE_STATUSES)})",
            name='ck_legal_issues_status',
        ),
        sa.CheckConstraint(
            'confidence >= 0.0 AND confidence <= 1.0',
            name='ck_legal_issues_confidence',
        ),
        sa.ForeignKeyConstraint(
            ['case_id', 'parent_issue_id'],
            ['legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issues_parent_hierarchy',
            ondelete='RESTRICT',
        ),
    )
    op.create_index('ix_legal_issues_tenant_case', 'legal_issues', ['tenant_id', 'case_id'])
    op.create_index('ix_legal_issues_case_parent', 'legal_issues', ['case_id', 'parent_issue_id'])


def downgrade() -> None:
    op.drop_index('ix_legal_issues_case_parent', table_name='legal_issues')
    op.drop_index('ix_legal_issues_tenant_case', table_name='legal_issues')
    op.drop_table('legal_issues')
