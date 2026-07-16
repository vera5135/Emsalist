"""add P2.8B evidence sufficiency assessment table

Revision ID: 4a5b6c7d8e9f
Revises: 3a4b5c6d7e8f
Create Date: 2026-07-15 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a5b6c7d8e9f'
down_revision: Union[str, Sequence[str], None] = '3a4b5c6d7e8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVIDENCE_STATUSES = (
    'authenticity_risk', 'contradicted', 'inadmissibility_risk',
    'partially_supported', 'supported', 'unsupported',
)


def upgrade() -> None:
    op.create_table(
        'evidence_sufficiency_assessments',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('claim_id', sa.String(length=32), nullable=False),
        sa.Column('evidence_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('legal_source_refs', sa.JSON(), nullable=False),
        sa.Column('fact_refs', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_evidence_sufficiency_assessments_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_evidence_sufficiency_assessments_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_evidence_sufficiency_assessments_issue',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'claim_id'],
            ['claims.tenant_id', 'claims.case_id', 'claims.id'],
            name='fk_evidence_sufficiency_assessments_claim',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'evidence_id'],
            ['evidence.tenant_id', 'evidence.case_id', 'evidence.id'],
            name='fk_evidence_sufficiency_assessments_evidence',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _EVIDENCE_STATUSES)})",
            name='ck_evidence_sufficiency_assessments_status',
        ),
    )
    op.create_index(
        'ix_evidence_sufficiency_assessments_tenant_case',
        'evidence_sufficiency_assessments',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_evidence_sufficiency_assessments_issue',
        'evidence_sufficiency_assessments',
        ['case_id', 'issue_id'],
    )
    op.create_index(
        'ix_evidence_sufficiency_assessments_claim',
        'evidence_sufficiency_assessments',
        ['case_id', 'claim_id'],
    )
    op.create_index(
        'ix_evidence_sufficiency_assessments_evidence',
        'evidence_sufficiency_assessments',
        ['case_id', 'evidence_id'],
    )
    op.create_index(
        'uq_evidence_sufficiency_assessments_active_scope',
        'evidence_sufficiency_assessments',
        ['tenant_id', 'case_id', 'issue_id', 'claim_id', 'evidence_id'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_evidence_sufficiency_assessments_active_scope', table_name='evidence_sufficiency_assessments')
    op.drop_index('ix_evidence_sufficiency_assessments_evidence', table_name='evidence_sufficiency_assessments')
    op.drop_index('ix_evidence_sufficiency_assessments_claim', table_name='evidence_sufficiency_assessments')
    op.drop_index('ix_evidence_sufficiency_assessments_issue', table_name='evidence_sufficiency_assessments')
    op.drop_index('ix_evidence_sufficiency_assessments_tenant_case', table_name='evidence_sufficiency_assessments')
    op.drop_table('evidence_sufficiency_assessments')
