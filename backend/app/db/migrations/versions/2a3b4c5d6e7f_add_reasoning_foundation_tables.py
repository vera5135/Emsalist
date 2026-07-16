"""add P2.8B reasoning foundation tables

Revision ID: 2a3b4c5d6e7f
Revises: 1a2b3c4d5e6f
Create Date: 2026-07-15 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a3b4c5d6e7f'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'memory_revisions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('memory_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('trigger_type', sa.String(length=40), nullable=False),
        sa.Column('trigger_id', sa.String(length=64), nullable=False),
        sa.Column('change_summary_json', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_memory_revisions_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_memory_revisions_case'),
        sa.UniqueConstraint('tenant_id', 'case_id', 'id', name='uq_memory_revisions_tenant_case_id'),
        sa.UniqueConstraint('tenant_id', 'case_id', 'revision_number', name='uq_memory_revisions_case_number'),
        sa.UniqueConstraint('tenant_id', 'case_id', 'memory_fingerprint', name='uq_memory_revisions_case_fingerprint'),
        sa.CheckConstraint(
            "trigger_type IN ('document_analysis', 'manual_edit', 'system_recompute', 'user_message', 'uyap_sync')",
            name='ck_memory_revisions_trigger_type',
        ),
        sa.CheckConstraint('length(memory_fingerprint) = 64', name='ck_memory_revisions_fingerprint_len'),
    )
    op.create_index('ix_memory_revisions_tenant_case', 'memory_revisions', ['tenant_id', 'case_id'])

    op.create_table(
        'legal_reasoning_runs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('memory_revision_id', sa.String(length=32), nullable=False),
        sa.Column('source_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('model_version', sa.String(length=80), nullable=False),
        sa.Column('prompt_version', sa.String(length=40), nullable=False),
        sa.Column('output_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('safe_summary_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_legal_reasoning_runs_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_legal_reasoning_runs_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'memory_revision_id'],
            ['memory_revisions.tenant_id', 'memory_revisions.case_id', 'memory_revisions.id'],
            name='fk_legal_reasoning_runs_memory_revision',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'stale', 'started', 'succeeded')",
            name='ck_legal_reasoning_runs_status',
        ),
        sa.CheckConstraint('length(source_fingerprint) = 64', name='ck_legal_reasoning_runs_source_fingerprint_len'),
        sa.CheckConstraint('length(output_hash) = 64', name='ck_legal_reasoning_runs_output_hash_len'),
    )
    op.create_index('ix_legal_reasoning_runs_tenant_case', 'legal_reasoning_runs', ['tenant_id', 'case_id'])
    op.create_index('ix_legal_reasoning_runs_case_created', 'legal_reasoning_runs', ['case_id', 'created_at'])
    op.create_index(
        'ix_legal_reasoning_runs_reproducibility',
        'legal_reasoning_runs',
        ['case_id', 'memory_revision_id', 'source_fingerprint', 'prompt_version', 'provider', 'model_version'],
    )


def downgrade() -> None:
    op.drop_index('ix_legal_reasoning_runs_reproducibility', table_name='legal_reasoning_runs')
    op.drop_index('ix_legal_reasoning_runs_case_created', table_name='legal_reasoning_runs')
    op.drop_index('ix_legal_reasoning_runs_tenant_case', table_name='legal_reasoning_runs')
    op.drop_table('legal_reasoning_runs')
    op.drop_index('ix_memory_revisions_tenant_case', table_name='memory_revisions')
    op.drop_table('memory_revisions')
