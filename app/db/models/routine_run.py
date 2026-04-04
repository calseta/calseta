"""RoutineRun ORM model — tracks each execution of a routine."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AppendOnlyTimestampMixin, Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_routine import AgentRoutine
    from app.db.models.routine_trigger import RoutineTrigger


class RoutineRun(AppendOnlyTimestampMixin, UUIDMixin, Base):
    __tablename__ = "routine_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_routines.id", ondelete="CASCADE"), nullable=False
    )
    trigger_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("routine_triggers.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)  # cron, webhook, manual
    status: Mapped[str] = mapped_column(Text, nullable=False, default="received")
    trigger_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    linked_alert_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    linked_issue_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_issues.id", ondelete="SET NULL"), nullable=True
    )
    heartbeat_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("heartbeat_runs.id", ondelete="SET NULL"), nullable=True
    )
    coalesced_into_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("routine_runs.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    routine: Mapped[AgentRoutine] = relationship("AgentRoutine", back_populates="runs")
    trigger: Mapped[RoutineTrigger] = relationship("RoutineTrigger", foreign_keys=[trigger_id])
