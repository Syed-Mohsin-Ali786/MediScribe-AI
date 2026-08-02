"""add doctor avatar + permission request columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    op.add_column(
        "users",
        sa.Column("permission_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("permission_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("users", "permission_requested", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "permission_requested_at")
    op.drop_column("users", "permission_requested")
    op.drop_column("users", "avatar_url")
