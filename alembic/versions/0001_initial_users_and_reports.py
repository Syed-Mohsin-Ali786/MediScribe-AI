"""initial users and reports tables

Revision ID: 0001
Revises:
Create Date: 2026-07-31

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("specialization", sa.String(length=255), nullable=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_doctor_id", "users", ["doctor_id"], unique=False)

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audio_url", sa.String(length=2048), nullable=False),
        sa.Column("transcript_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_doctor_id", "reports", ["doctor_id"], unique=False)
    op.create_index("ix_reports_patient_id", "reports", ["patient_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reports_patient_id", table_name="reports")
    op.drop_index("ix_reports_doctor_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_users_doctor_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
