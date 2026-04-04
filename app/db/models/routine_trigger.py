"""RoutineTrigger ORM model — cron/webhook/manual trigger for a routine."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_routine import AgentRoutine


class RoutineTrigger(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "routine_triggers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_routines.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # cron, webhook, manual
    cron_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True, default="UTC")
    webhook_public_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    webhook_secret_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_replay_window_sec: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=300
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    routine: Mapped[AgentRoutine] = relationship("AgentRoutine", back_populates="triggers")
