"""add typed evidence_claim_links table (P2.8A5)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVIDENCE_CLAIM_RELATIONS = (
    'evidence_contradicts_claim', 'evidence_supports_claim',
)


def upgrade() -> None:
    op.create_table(
        'evidence_claim_links',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('claim_id', sa.String(length=32), nullable=False),
        sa.Column('evidence_id', sa.String(length=32), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_evidence_claim_links_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_evidence_claim_links_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'claim_id'],
            ['claims.tenant_id', 'claims.case_id', 'claims.id'],
            name='fk_evidence_claim_links_claim',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'evidence_id'],
            ['evidence.tenant_id', 'evidence.case_id', 'evidence.id'],
            name='fk_evidence_claim_links_evidence',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in _EVIDENCE_CLAIM_RELATIONS)})",
            name='ck_evidence_claim_links_relation_type',
        ),
    )
    op.create_index(
        'ix_evidence_claim_links_tenant_case',
        'evidence_claim_links',
        ['tenant_id', 'case_id'],
    )
    op.create_index(
        'ix_evidence_claim_links_claim',
        'evidence_claim_links',
        ['case_id', 'claim_id'],
    )
    op.create_index(
        'ix_evidence_claim_links_evidence',
        'evidence_claim_links',
        ['case_id', 'evidence_id'],
    )
    op.create_index(
        'uq_evidence_claim_links_active_relation',
        'evidence_claim_links',
        ['tenant_id', 'case_id', 'claim_id', 'evidence_id', 'relation_type'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
        sqlite_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_evidence_claim_links_active_relation', table_name='evidence_claim_links')
    op.drop_index('ix_evidence_claim_links_evidence', table_name='evidence_claim_links')
    op.drop_index('ix_evidence_claim_links_claim', table_name='evidence_claim_links')
    op.drop_index('ix_evidence_claim_links_tenant_case', table_name='evidence_claim_links')
    op.drop_table('evidence_claim_links')
