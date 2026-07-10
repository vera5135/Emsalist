"""P2.2B2A — Add Apple auth identity and link ticket tables.

Creates auth_identities (provider-linked accounts) and auth_link_tickets
(one-time use link tickets for Apple account binding).

Revision ID: b3c4d5e6f7a8
Revises: a1a2a3a4a5a6
Create Date: 2026-07-10 00:00:00.000000
"""
from __future__ import annotations
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a1a2a3a4a5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False, server_default="apple"),
        sa.Column("provider_subject_hash", sa.String(128), nullable=False),
        sa.Column("provider_audience", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_audience", "provider_subject_hash", name="uq_auth_identity_provider_subject"),
        sa.UniqueConstraint("provider", "user_id", name="uq_auth_identity_provider_user"),
        sa.Index("ix_auth_identity_provider_lookup", "provider", "provider_audience", "provider_subject_hash"),
        sa.Index("ix_auth_identity_user", "user_id"),
        sa.Index("ix_auth_identity_tenant_user", "tenant_id", "user_id"),
    )

    op.create_table(
        "auth_link_tickets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("ticket_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="apple"),
        sa.Column("provider_subject_hash", sa.String(128), nullable=False),
        sa.Column("provider_audience", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index("ix_auth_link_ticket_hash", "ticket_hash"),
        sa.Index("ix_auth_link_ticket_expires", "expires_at"),
    )


def downgrade() -> None:
    op.drop_table("auth_link_tickets")
    op.drop_table("auth_identities")
