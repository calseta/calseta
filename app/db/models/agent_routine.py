"""AgentRoutine ORM model — defines recurring work patterns for agents."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.routine_run import RoutineRun
    from app.db.models.routine_trigger import RoutineTrigger


class AgentRoutine(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_routines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_registrations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    concurrency_policy: Mapped[str] = mapped_column(Text, nullable=False, default="skip_if_active")
    catch_up_policy: Mapped[str] = mapped_column(Text, nullable=False, default="skip_missed")
    task_template: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    max_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent_registration: Mapped[AgentRegistration] = relationship(
        "AgentRegistration", foreign_keys=[agent_registration_id]
    )
    triggers: Mapped[list[RoutineTrigger]] = relationship(
        "RoutineTrigger", back_populates="routine", cascade="all, delete-orphan"
    )
    runs: Mapped[list[RoutineRun]] = relationship(
        "RoutineRun", back_populates="routine", cascade="all, delete-orphan"
    )
