"""HeartbeatRun ORM model — tracks agent invocation lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class HeartbeatRun(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "heartbeat_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="scheduler")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    alerts_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    actions_proposed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
