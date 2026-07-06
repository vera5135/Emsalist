"""fix_nullable_constraints_and_indexes

Revision ID: f00d796771c5
Revises: c6d0712082f7
Create Date: 2026-07-07 02:10:00.000000

Correct nullable mismatches between SQLAlchemy models and existing
PostgreSQL tables.  The original migrations omitted explicit nullable=False
on several columns whose Mapped types are non-optional.

Also reconciles index names:
  - Drops obsolete indexes not present in the current model metadata
  - Creates missing model-defined indexes
  - Renames legal issue node/edge indexes to match model definitions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f00d796771c5'
down_revision: Union[str, Sequence[str], None] = 'c6d0712082f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1.  Backfill NULLs → safe defaults ────────────────────────
    #
    # String  → ''
    # Boolean → false
    # Integer → 0
    # Datetime → now()

    # backup_runs
    op.execute(
        sa.text(
            "UPDATE backup_runs SET correlation_id = ''      WHERE correlation_id      IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET schema_revision = ''      WHERE schema_revision     IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET application_version = ''  WHERE application_version IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET encrypted = false         WHERE encrypted           IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET manifest_sha256 = ''      WHERE manifest_sha256     IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET total_size_bytes = 0      WHERE total_size_bytes    IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET item_count = 0            WHERE item_count          IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET warning_count = 0         WHERE warning_count       IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET failure_count = 0         WHERE failure_count       IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET created_at = CURRENT_TIMESTAMP WHERE created_at     IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_runs SET updated_at = CURRENT_TIMESTAMP WHERE updated_at     IS NULL"
        )
    )

    # backup_items
    op.execute(
        sa.text(
            "UPDATE backup_items SET size_bytes  = 0          WHERE size_bytes          IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_items SET sha256      = ''         WHERE sha256              IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE backup_items SET created_at  = CURRENT_TIMESTAMP WHERE created_at   IS NULL"
        )
    )

    # restore_items
    op.execute(
        sa.text(
            "UPDATE restore_items SET created_at = CURRENT_TIMESTAMP WHERE created_at   IS NULL"
        )
    )

    # restore_runs
    op.execute(
        sa.text(
            "UPDATE restore_runs SET dry_run = false          WHERE dry_run             IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET validation_only = false  WHERE validation_only     IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET schema_revision_before = ''  WHERE schema_revision_before IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET schema_revision_after  = '' WHERE schema_revision_after  IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET restored_item_count = 0  WHERE restored_item_count IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET skipped_item_count = 0   WHERE skipped_item_count  IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET failed_item_count = 0    WHERE failed_item_count   IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET created_at = CURRENT_TIMESTAMP WHERE created_at    IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE restore_runs SET updated_at = CURRENT_TIMESTAMP WHERE updated_at    IS NULL"
        )
    )

    # ── 2.  Alter columns → NOT NULL ──────────────────────────────

    # backup_runs
    with op.batch_alter_table("backup_runs", schema=None) as batch_op:
        batch_op.alter_column("correlation_id", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("schema_revision", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("application_version", existing_type=sa.String(20), nullable=False)
        batch_op.alter_column("encrypted", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("manifest_sha256", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("total_size_bytes", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("item_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("warning_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("failure_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    # backup_items
    with op.batch_alter_table("backup_items", schema=None) as batch_op:
        batch_op.alter_column("size_bytes", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("sha256", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    # restore_items
    with op.batch_alter_table("restore_items", schema=None) as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    # restore_runs
    with op.batch_alter_table("restore_runs", schema=None) as batch_op:
        batch_op.alter_column("dry_run", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("validation_only", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("schema_revision_before", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("schema_revision_after", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("restored_item_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("skipped_item_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("failed_item_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    # ── 3.  Index reconciliation ─────────────────────────────────

    # 3a.  Remove obsolete indexes not present in model metadata
    op.execute(sa.text("DROP INDEX IF EXISTS ix_backup_items_run"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_backup_runs_tenant"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_restore_runs_status"))

    # 3b.  Remove old legal issue node indexes
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_nodes_tenant_case"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_nodes_case_type"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_nodes_source"))

    # 3c.  Remove old legal issue edge indexes
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_edges_tenant_case"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_edges_source"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_issue_edges_target"))

    # 3d.  Create new legal issue node indexes (model expects these names)
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lgn_tenant_case ON legal_issue_nodes (tenant_id, case_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lgn_case_type ON legal_issue_nodes (case_id, node_type)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lgn_source ON legal_issue_nodes (source_type, source_id)"))

    # 3e.  Create new legal issue edge indexes (model expects these names)
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lge_tenant_case ON legal_issue_edges (tenant_id, case_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lge_source ON legal_issue_edges (source_node_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_lge_target ON legal_issue_edges (target_node_id)"))


def downgrade() -> None:
    # ── 3e.  Remove new legal issue edge indexes ──────────────────
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lge_target"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lge_source"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lge_tenant_case"))

    # ── 3d.  Remove new legal issue node indexes ─────────────────
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lgn_source"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lgn_case_type"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lgn_tenant_case"))

    # ── 3c.  Restore old legal issue edge indexes ────────────────
    op.create_index("ix_legal_issue_edges_target", "legal_issue_edges", ["target_node_id"])
    op.create_index("ix_legal_issue_edges_source", "legal_issue_edges", ["source_node_id"])
    op.create_index("ix_legal_issue_edges_tenant_case", "legal_issue_edges", ["tenant_id", "case_id"])

    # ── 3b.  Restore old legal issue node indexes ────────────────
    op.create_index("ix_legal_issue_nodes_source", "legal_issue_nodes", ["source_type", "source_id"])
    op.create_index("ix_legal_issue_nodes_case_type", "legal_issue_nodes", ["case_id", "node_type"])
    op.create_index("ix_legal_issue_nodes_tenant_case", "legal_issue_nodes", ["tenant_id", "case_id"])

    # ── 3a.  Restore obsolete indexes ────────────────────────────
    op.create_index("ix_restore_runs_status", "restore_runs", ["status"])
    op.create_index("ix_backup_runs_tenant", "backup_runs", ["tenant_id"])
    op.create_index("ix_backup_items_run", "backup_items", ["backup_run_id"])

    # ── 2.  Revert NOT NULL → nullable ───────────────────────────
    # restore_runs
    with op.batch_alter_table("restore_runs", schema=None) as batch_op:
        batch_op.alter_column("dry_run", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("validation_only", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("schema_revision_before", existing_type=sa.String(32), nullable=True)
        batch_op.alter_column("schema_revision_after", existing_type=sa.String(32), nullable=True)
        batch_op.alter_column("restored_item_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("skipped_item_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("failed_item_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    # restore_items
    with op.batch_alter_table("restore_items", schema=None) as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    # backup_items
    with op.batch_alter_table("backup_items", schema=None) as batch_op:
        batch_op.alter_column("sha256", existing_type=sa.String(64), nullable=True)
        batch_op.alter_column("size_bytes", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    # backup_runs
    with op.batch_alter_table("backup_runs", schema=None) as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.alter_column("failure_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("warning_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("item_count", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("total_size_bytes", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("manifest_sha256", existing_type=sa.String(64), nullable=True)
        batch_op.alter_column("encrypted", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("application_version", existing_type=sa.String(20), nullable=True)
        batch_op.alter_column("schema_revision", existing_type=sa.String(32), nullable=True)
        batch_op.alter_column("correlation_id", existing_type=sa.String(32), nullable=True)
