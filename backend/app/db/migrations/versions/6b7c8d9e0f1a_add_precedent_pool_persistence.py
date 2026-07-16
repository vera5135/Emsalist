"""add precedent pool persistence

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b7c8d9e0f1a"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "precedent_pools",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=False),
        sa.Column("initiated_by", sa.String(32), nullable=False),
        sa.Column("profile_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("query_strategies_json", sa.JSON(), nullable=False),
        sa.Column("provider_code", sa.String(30), nullable=False, server_default="yargitay"),
        sa.Column("candidate_cap", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("safe_error_code", sa.String(50), nullable=False, server_default=""),
        sa.Column("provider_status", sa.String(40), nullable=False, server_default=""),
        sa.Column("source_ingestion_run_ids", sa.JSON(), nullable=False),
        sa.Column("profile_summary_json", sa.JSON(), nullable=False),
        sa.Column("stats_json", sa.JSON(), nullable=False),
        sa.Column("planner_version", sa.String(60), nullable=False, server_default="p2.8-final-planner-1"),
        sa.Column("model_version", sa.String(60), nullable=False, server_default="deterministic_v1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"]),
        sa.UniqueConstraint(
            "tenant_id", "case_id", "profile_fingerprint", "provider_code",
            name="uq_precedent_pools_case_profile_provider",
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','completed_with_errors','degraded_existing_corpus','failed')",
            name="ck_precedent_pools_status",
        ),
    )
    op.create_index(
        "ix_precedent_pools_tenant_case",
        "precedent_pools",
        ["tenant_id", "case_id", "created_at"],
    )
    op.create_index("ix_precedent_pools_profile", "precedent_pools", ["profile_fingerprint"])

    op.create_table(
        "precedent_pool_decisions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("pool_id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=False),
        sa.Column("source_record_id", sa.String(32), nullable=False),
        sa.Column("source_version_id", sa.String(32), nullable=False),
        sa.Column("selected_source_paragraph_ids", sa.JSON(), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scores_json", sa.JSON(), nullable=False),
        sa.Column("selection_state", sa.String(30), nullable=False, server_default="shortlisted"),
        sa.Column("duplicate_of_decision_id", sa.String(32), nullable=True),
        sa.Column("match_reasons_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["precedent_pools.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"]),
        sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"]),
        sa.ForeignKeyConstraint(
            ["source_record_id", "source_version_id"],
            ["source_versions.source_record_id", "source_versions.id"],
            name="fk_pool_decision_exact_source_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "pool_id", "source_record_id", "source_version_id",
            name="uq_pool_decision_source_version",
        ),
        sa.CheckConstraint(
            "selection_state IN ('candidate','shortlisted','accepted','rejected','duplicate')",
            name="ck_pool_decision_selection_state",
        ),
    )
    op.create_index("ix_pool_decisions_pool_rank", "precedent_pool_decisions", ["pool_id", "retrieval_rank"])
    op.create_index("ix_pool_decisions_tenant_case", "precedent_pool_decisions", ["tenant_id", "case_id"])
    op.create_index("ix_pool_decisions_source", "precedent_pool_decisions", ["source_record_id", "source_version_id"])

    op.create_table(
        "precedent_decision_analyses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("pool_id", sa.String(32), nullable=False),
        sa.Column("pool_decision_id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=False),
        sa.Column("source_record_id", sa.String(32), nullable=False),
        sa.Column("source_version_id", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="deterministic"),
        sa.Column("model_version", sa.String(80), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(80), nullable=False, server_default=""),
        sa.Column("schema_version", sa.String(40), nullable=False, server_default="p2.8-analysis-v1"),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("output_fingerprint", sa.String(64), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="current"),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["precedent_pools.id"]),
        sa.ForeignKeyConstraint(["pool_decision_id"], ["precedent_pool_decisions.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"]),
        sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"]),
        sa.ForeignKeyConstraint(
            ["source_record_id", "source_version_id"],
            ["source_versions.source_record_id", "source_versions.id"],
            name="fk_decision_analysis_exact_source_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "pool_decision_id", "source_version_id", "source_fingerprint", "output_fingerprint",
            name="uq_decision_analysis_exact_output",
        ),
        sa.CheckConstraint(
            "status IN ('current','stale','failed')",
            name="ck_decision_analysis_status",
        ),
    )
    op.create_index("ix_decision_analyses_pool", "precedent_decision_analyses", ["pool_id", "created_at"])
    op.create_index("ix_decision_analyses_tenant_case", "precedent_decision_analyses", ["tenant_id", "case_id"])


def downgrade() -> None:
    op.drop_index("ix_decision_analyses_tenant_case", table_name="precedent_decision_analyses")
    op.drop_index("ix_decision_analyses_pool", table_name="precedent_decision_analyses")
    op.drop_table("precedent_decision_analyses")
    op.drop_index("ix_pool_decisions_source", table_name="precedent_pool_decisions")
    op.drop_index("ix_pool_decisions_tenant_case", table_name="precedent_pool_decisions")
    op.drop_index("ix_pool_decisions_pool_rank", table_name="precedent_pool_decisions")
    op.drop_table("precedent_pool_decisions")
    op.drop_index("ix_precedent_pools_profile", table_name="precedent_pools")
    op.drop_index("ix_precedent_pools_tenant_case", table_name="precedent_pools")
    op.drop_table("precedent_pools")
