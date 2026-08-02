from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class JSONBCompat(TypeDecorator):
    """JSON column that renders as JSONB on PostgreSQL and plain JSON elsewhere.

    Lets the same models run against Supabase Postgres (JSONB) and a local
    SQLite demo database (JSON) without schema changes.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

            return dialect.type_descriptor(PGJSONB())
        return dialect.type_descriptor(JSON())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class UUIDMixin:
    id: Mapped[_uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )
