"""
SQLAlchemy 2.0 declarative base and shared column mixins.

Every model inherits from Base and uses TimestampMixin + UUIDMixin,
EXCEPT ActivityEvent which omits updated_at (it is append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns. Both server-defaulted."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AppendOnlyTimestampMixin:
    """Adds only created_at. For append-only tables (activity_events)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """Adds uuid column. Server default uses gen_random_uuid() (requires pgcrypto)."""

    uuid: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        unique=True,
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
