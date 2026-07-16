"""add typed legal_issue_risk_links table (P2.8A6)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-15 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legal_issue_risk_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('risk_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_issue_risk_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_issue_risk_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issue_risk_links_issue',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'risk_id'],
            ['risks.tenant_id', 'risks.case_id', 'risks.id'],
            name='fk_legal_issue_risk_links_risk',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "relation_type IN ('issue_affects_risk')",
            name='ck_legal_issue_risk_links_relation_type',
        ),
    )
    op.create_index(
        'ix_legal_issue_risk_links_tenant_case',
        'legal_issue_risk_links',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_legal_issue_risk_links_issue',
        'legal_issue_risk_links',
        ['case_id', 'issue_id'],
    )
    op.create_index(
        'ix_legal_issue_risk_links_risk',
        'legal_issue_risk_links',
        ['case_id', 'risk_id'],
    )
    op.create_index(
        'uq_legal_issue_risk_links_active_relation',
        'legal_issue_risk_links',
        ['tenant_id', 'case_id', 'issue_id', 'risk_id', 'relation_type'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_legal_issue_risk_links_active_relation', table_name='legal_issue_risk_links')
    op.drop_index('ix_legal_issue_risk_links_risk', table_name='legal_issue_risk_links')
    op.drop_index('ix_legal_issue_risk_links_issue', table_name='legal_issue_risk_links')
    op.drop_index('ix_legal_issue_risk_links_tenant_case', table_name='legal_issue_risk_links')
    op.drop_table('legal_issue_risk_links')
