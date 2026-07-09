"""P2.2B1 — Add missing User auth columns.

Adds password_hash, failed_login_count, locked_until, token_version,
last_login_at, password_changed_at to the users table with appropriate defaults.
Backfills default values for existing user rows.

Revision ID: a1a2a3a4a5a6
Revises: f00d796771c5
Create Date: 2026-07-09 00:00:00.000000
"""
from __future__ import annotations
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1a2a3a4a5a6"
down_revision: str | None = "f00d796771c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "token_version")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "password_hash")
