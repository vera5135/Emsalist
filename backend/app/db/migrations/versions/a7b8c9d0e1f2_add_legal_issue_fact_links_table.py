"""add typed legal_issue_fact_links table (P2.8A3)

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-07-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FACT_RELATIONS = (
    'fact_contradicts_issue', 'fact_supports_issue',
)


def upgrade() -> None:
    op.create_table(
        'legal_issue_fact_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('fact_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_issue_fact_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_issue_fact_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_legal_issue_fact_links_issue',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'fact_id'],
            ['case_facts.tenant_id', 'case_facts.case_id', 'case_facts.id'],
            name='fk_legal_issue_fact_links_fact',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in _FACT_RELATIONS)})",
            name='ck_legal_issue_fact_links_relation_type',
        ),
    )
    op.create_index(
        'ix_legal_issue_fact_links_tenant_case',
        'legal_issue_fact_links',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_legal_issue_fact_links_issue',
        'legal_issue_fact_links',
        ['case_id', 'issue_id'],
    )
    op.create_index(
        'ix_legal_issue_fact_links_fact',
        'legal_issue_fact_links',
        ['case_id', 'fact_id'],
    )
    op.create_index(
        'uq_legal_issue_fact_links_active_relation',
        'legal_issue_fact_links',
        ['tenant_id', 'case_id', 'issue_id', 'fact_id', 'relation_type'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_legal_issue_fact_links_active_relation', table_name='legal_issue_fact_links')
    op.drop_index('ix_legal_issue_fact_links_fact', table_name='legal_issue_fact_links')
    op.drop_index('ix_legal_issue_fact_links_issue', table_name='legal_issue_fact_links')
    op.drop_index('ix_legal_issue_fact_links_tenant_case', table_name='legal_issue_fact_links')
    op.drop_table('legal_issue_fact_links')
