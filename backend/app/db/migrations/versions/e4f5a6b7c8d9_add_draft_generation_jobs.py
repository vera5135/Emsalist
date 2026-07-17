"""add draft generation jobs table (P2.9C3A)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'draft_generation_jobs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=False),
        sa.Column('draft_document_id', sa.String(length=32), nullable=False),
        sa.Column('requested_by_user_id', sa.String(length=32), nullable=False,
                  server_default=''),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='queued'),
        sa.Column('stage', sa.String(length=30), nullable=False,
                  server_default='queued'),
        sa.Column('progress_percent', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('requested_draft_version', sa.Integer(), nullable=False),
        sa.Column('client_request_id', sa.String(length=36), nullable=False,
                  server_default=''),
        sa.Column('request_fingerprint', sa.String(length=64), nullable=False,
                  server_default=''),
        sa.Column('provider_name', sa.String(length=40), nullable=True),
        sa.Column('model_name', sa.String(length=80), nullable=True),
        sa.Column('result_draft_version', sa.Integer(), nullable=True),
        sa.Column('safe_error_code', sa.String(length=100), nullable=True),
        sa.Column('logical_call_count', sa.Integer(), nullable=True),
        sa.Column('request_attempt_count', sa.Integer(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('reasoning_tokens', sa.Integer(), nullable=True),
        sa.Column('finish_reasons_json', sa.JSON(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('lease_owner', sa.String(length=64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('failed', 'queued', 'running', 'succeeded')",
            name='ck_draft_generation_jobs_status',
        ),
        sa.CheckConstraint(
            "stage IN ('completed', 'failed', 'persisting', 'preflight', "
            "'preparing_input', 'provider_generation', 'queued', "
            "'validating_output')",
            name='ck_draft_generation_jobs_stage',
        ),
        sa.CheckConstraint(
            'progress_percent >= 0 AND progress_percent <= 100',
            name='ck_draft_generation_jobs_progress',
        ),
        sa.CheckConstraint(
            'attempt_count >= 0',
            name='ck_draft_generation_jobs_attempt_count',
        ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_draft_generation_jobs_tenant'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'],
                                name='fk_draft_generation_jobs_case'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'case_id', 'draft_document_id'],
            ['draft_documents.tenant_id', 'draft_documents.case_id',
             'draft_documents.id'],
            name='fk_draft_generation_jobs_draft_document',
            ondelete='RESTRICT',
        ),
        sa.UniqueConstraint(
            'tenant_id', 'case_id', 'draft_document_id', 'client_request_id',
            name='uq_draft_generation_jobs_request_id',
        ),
    )
    op.create_index(
        'uq_draft_generation_jobs_active_per_draft',
        'draft_generation_jobs',
        ['tenant_id', 'case_id', 'draft_document_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index('ix_draft_generation_jobs_tenant_case',
                    'draft_generation_jobs', ['tenant_id', 'case_id'])
    op.create_index('ix_draft_generation_jobs_draft',
                    'draft_generation_jobs', ['draft_document_id'])
    op.create_index('ix_draft_generation_jobs_status',
                    'draft_generation_jobs', ['status'])


def downgrade() -> None:
    op.drop_index('ix_draft_generation_jobs_status',
                  table_name='draft_generation_jobs')
    op.drop_index('ix_draft_generation_jobs_draft',
                  table_name='draft_generation_jobs')
    op.drop_index('ix_draft_generation_jobs_tenant_case',
                  table_name='draft_generation_jobs')
    op.drop_index('uq_draft_generation_jobs_active_per_draft',
                  table_name='draft_generation_jobs')
    op.drop_table('draft_generation_jobs')
