"""add typed legal_issue_dependencies table (P2.8A2)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legal_issue_dependencies',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('required_issue_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_issue_dependencies_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_issue_dependencies_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issue_dependencies_issue',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'required_issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issue_dependencies_required_issue',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            'issue_id <> required_issue_id',
            name='ck_legal_issue_dependencies_no_self',
        ),
    )
    op.create_index(
        'ix_legal_issue_dependencies_tenant_case',
        'legal_issue_dependencies',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_legal_issue_dependencies_issue',
        'legal_issue_dependencies',
        ['case_id', 'issue_id'],
    )
    op.create_index(
        'ix_legal_issue_dependencies_required_issue',
        'legal_issue_dependencies',
        ['case_id', 'required_issue_id'],
    )
    op.create_index(
        'uq_legal_issue_dependencies_active_pair',
        'legal_issue_dependencies',
        ['tenant_id', 'case_id', 'issue_id', 'required_issue_id'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_legal_issue_dependencies_active_pair', table_name='legal_issue_dependencies')
    op.drop_index('ix_legal_issue_dependencies_required_issue', table_name='legal_issue_dependencies')
    op.drop_index('ix_legal_issue_dependencies_issue', table_name='legal_issue_dependencies')
    op.drop_index('ix_legal_issue_dependencies_tenant_case', table_name='legal_issue_dependencies')
    op.drop_table('legal_issue_dependencies')
