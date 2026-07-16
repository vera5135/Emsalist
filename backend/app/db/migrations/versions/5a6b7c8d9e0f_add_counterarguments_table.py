"""add counterarguments table

Revision ID: 5a6b7c8d9e0f
Revises: 4a5b6c7d8e9f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, Sequence[str], None] = "4a5b6c7d8e9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counterarguments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=False),
        sa.Column("issue_id", sa.String(32), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("basis", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(30), nullable=False, server_default="proposed"),
        sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_counterarguments_issue", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "category IN ('alternative_fact_interpretation','missing_evidence','opposing_precedent','procedural_time_bar','overbroad_request')",
            name="ck_counterarguments_category",
        ),
        sa.CheckConstraint(
            "status IN ('proposed','accepted','rejected','needs_review')",
            name="ck_counterarguments_status",
        ),
    )
    op.create_index("ix_counterarguments_tenant_case", "counterarguments", ["tenant_id", "case_id"])
    op.create_index("ix_counterarguments_issue", "counterarguments", ["case_id", "issue_id"])


def downgrade() -> None:
    op.drop_index("ix_counterarguments_issue", table_name="counterarguments")
    op.drop_index("ix_counterarguments_tenant_case", table_name="counterarguments")
    op.drop_table("counterarguments")
