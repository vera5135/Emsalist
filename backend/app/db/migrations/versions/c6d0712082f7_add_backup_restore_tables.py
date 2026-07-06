"""add_backup_restore_tables

Revision ID: c6d0712082f7
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06 03:14:02.272370
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6d0712082f7'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'backup_runs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('tenant_id', sa.String(32), nullable=True),
        sa.Column('backup_type', sa.String(30), nullable=False, default='full'),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('scope', sa.String(20), nullable=False, default='full'),
        sa.Column('storage_backend', sa.String(30), nullable=False, default='local'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(32), nullable=True),
        sa.Column('correlation_id', sa.String(32), default=''),
        sa.Column('schema_revision', sa.String(32), default=''),
        sa.Column('application_version', sa.String(20), default=''),
        sa.Column('encrypted', sa.Boolean, default=False),
        sa.Column('manifest_sha256', sa.String(64), default=''),
        sa.Column('total_size_bytes', sa.Integer, default=0),
        sa.Column('item_count', sa.Integer, default=0),
        sa.Column('warning_count', sa.Integer, default=0),
        sa.Column('failure_count', sa.Integer, default=0),
        sa.Column('safe_summary', sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_backup_runs_status_time', 'backup_runs', ['status', 'created_at'])
    op.create_index('ix_backup_runs_retention', 'backup_runs', ['retention_until'])
    op.create_index('ix_backup_runs_tenant', 'backup_runs', ['tenant_id'])

    op.create_table(
        'backup_items',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('backup_run_id', sa.String(32), sa.ForeignKey('backup_runs.id'), nullable=False),
        sa.Column('item_type', sa.String(30), nullable=False),
        sa.Column('logical_name', sa.String(500), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('size_bytes', sa.Integer, default=0),
        sa.Column('sha256', sa.String(64), default=''),
        sa.Column('encrypted_sha256', sa.String(64), nullable=True, default=None),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('failure_code', sa.String(50), nullable=True),
        sa.Column('safe_metadata', sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_backup_items_run_type', 'backup_items', ['backup_run_id', 'item_type'])
    op.create_index('ix_backup_items_run', 'backup_items', ['backup_run_id'])

    op.create_table(
        'restore_runs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('backup_run_id', sa.String(32), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('target_environment', sa.String(20), nullable=False, default='test'),
        sa.Column('dry_run', sa.Boolean, default=False),
        sa.Column('validation_only', sa.Boolean, default=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('initiated_by', sa.String(32), nullable=True),
        sa.Column('pre_restore_backup_id', sa.String(32), nullable=True),
        sa.Column('schema_revision_before', sa.String(32), default=''),
        sa.Column('schema_revision_after', sa.String(32), default=''),
        sa.Column('restored_item_count', sa.Integer, default=0),
        sa.Column('skipped_item_count', sa.Integer, default=0),
        sa.Column('failed_item_count', sa.Integer, default=0),
        sa.Column('safe_summary', sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_restore_runs_backup', 'restore_runs', ['backup_run_id'])
    op.create_index('ix_restore_runs_status', 'restore_runs', ['status'])

    op.create_table(
        'restore_items',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('restore_run_id', sa.String(32), sa.ForeignKey('restore_runs.id'), nullable=False),
        sa.Column('backup_item_id', sa.String(32), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('failure_code', sa.String(50), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('safe_metadata', sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_restore_items_run', 'restore_items', ['restore_run_id'])

    op.create_table(
        'backup_locks',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('lock_name', sa.String(50), nullable=False, unique=True),
        sa.Column('owner_id_hash', sa.String(64), nullable=False),
        sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_backup_locks_name', 'backup_locks', ['lock_name'], unique=True)


def downgrade() -> None:
    op.drop_table('backup_locks')
    op.drop_table('restore_items')
    op.drop_table('restore_runs')
    op.drop_table('backup_items')
    op.drop_table('backup_runs')
