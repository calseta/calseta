"""AgentTaskSession ORM model — persists LLM session state across heartbeats."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AgentTaskSession(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_task_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("alerts.id", ondelete="SET NULL"),
    )
    task_key: Mapped[str] = mapped_column(Text, nullable=False)
    session_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    session_display_id: Mapped[str | None] = mapped_column(Text)
    total_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    total_cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    heartbeat_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    last_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("heartbeat_runs.id", ondelete="SET NULL"),
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    compacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
