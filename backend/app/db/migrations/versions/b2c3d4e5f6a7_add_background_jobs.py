"""add_background_jobs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('background_jobs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=True),
        sa.Column('created_by', sa.String(length=32), nullable=True),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('safe_payload_hash', sa.String(length=64), nullable=False),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('safe_error_code', sa.String(length=50), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=False),
        sa.Column('progress_stage', sa.String(length=50), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('worker_id_hash', sa.String(length=64), nullable=True),
        sa.Column('parent_job_id', sa.String(length=32), nullable=True),
        sa.Column('correlation_id', sa.String(length=32), nullable=False),
        sa.Column('request_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bg_jobs_tenant', 'background_jobs', ['tenant_id'])
    op.create_index('ix_bg_jobs_case', 'background_jobs', ['case_id'])
    op.create_index('ix_bg_jobs_status', 'background_jobs', ['status'])
    op.create_index('ix_bg_jobs_tenant_status', 'background_jobs', ['tenant_id', 'status'])
    op.create_index('ix_bg_jobs_lease', 'background_jobs', ['status', 'lease_expires_at'])
    op.create_index('ix_bg_jobs_idem', 'background_jobs', ['tenant_id', 'idempotency_key'])

    op.create_table('background_job_attempts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worker_id_hash', sa.String(length=64), nullable=True),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('retryable', sa.Boolean(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('safe_metadata', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['background_jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bg_attempts_job', 'background_job_attempts', ['job_id'])

    op.create_table('background_job_events',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('progress_percent', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=50), nullable=True),
        sa.Column('safe_message', sa.String(length=500), nullable=True),
        sa.Column('safe_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['background_jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bg_events_job_seq', 'background_job_events', ['job_id', 'sequence_number'])

    op.create_table('background_job_artifacts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('case_id', sa.String(length=32), nullable=True),
        sa.Column('artifact_type', sa.String(length=30), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.ForeignKeyConstraint(['job_id'], ['background_jobs.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bg_artifacts_job', 'background_job_artifacts', ['job_id'])
    op.create_index('ix_bg_artifacts_tenant', 'background_job_artifacts', ['tenant_id', 'case_id'])


def downgrade() -> None:
    op.drop_table('background_job_artifacts')
    op.drop_table('background_job_events')
    op.drop_table('background_job_attempts')
    op.drop_table('background_jobs')
