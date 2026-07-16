"""add P2.8B burden of proof table

Revision ID: 3a4b5c6d7e8f
Revises: 2a3b4c5d6e7f
Create Date: 2026-07-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a4b5c6d7e8f'
down_revision: Union[str, Sequence[str], None] = '2a3b4c5d6e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BURDEN_STATUSES = (
    'candidate', 'finalized', 'review_required',
)

_EVIDENCE_STATUSES = (
    'authenticity_risk', 'contradicted', 'inadmissibility_risk',
    'partially_supported', 'supported', 'unsupported',
)


def upgrade() -> None:
    op.create_table(
        'burdens_of_proof',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('issue_id', sa.String(length=32), nullable=False),
        sa.Column('burden_party_id', sa.String(length=32), nullable=False),
        sa.Column('burden_type', sa.String(length=40), nullable=False),
        sa.Column('required_standard', sa.String(length=80), nullable=False),
        sa.Column('legal_source_refs', sa.JSON(), nullable=False),
        sa.Column('evidence_status', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_burdens_of_proof_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_burdens_of_proof_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'issue_id'],
            ['legal_issues.tenant_id', 'legal_issues.case_id', 'legal_issues.id'],
            name='fk_burdens_of_proof_issue',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _BURDEN_STATUSES)})",
            name='ck_burdens_of_proof_status',
        ),
        sa.CheckConstraint(
            f"evidence_status IN ({', '.join(repr(s) for s in _EVIDENCE_STATUSES)})",
            name='ck_burdens_of_proof_evidence_status',
        ),
        sa.CheckConstraint(
            "status <> 'finalized' OR json_array_length(legal_source_refs) > 0",
            name='ck_burdens_of_proof_finalized_requires_sources',
        ),
    )
    op.create_index('ix_burdens_of_proof_tenant_case', 'burdens_of_proof', ['tenant_id', 'case_id'])
    op.create_index('ix_burdens_of_proof_issue', 'burdens_of_proof', ['case_id', 'issue_id'])
    op.create_index(
        'uq_burdens_of_proof_active_scope',
        'burdens_of_proof',
        ['tenant_id', 'case_id', 'issue_id', 'burden_party_id', 'burden_type'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_burdens_of_proof_active_scope', table_name='burdens_of_proof')
    op.drop_index('ix_burdens_of_proof_issue', table_name='burdens_of_proof')
    op.drop_index('ix_burdens_of_proof_tenant_case', table_name='burdens_of_proof')
    op.drop_table('burdens_of_proof')
