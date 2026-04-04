"""AgentInvocation ORM model — parent→child agent delegation records."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.alert import Alert
    from app.db.models.alert_assignment import AlertAssignment


class AgentInvocation(TimestampMixin, UUIDMixin, Base):
    """Records a single delegation from an orchestrator to a specialist agent.

    Status state machine:
        queued → running → completed
                        → failed
                        → timed_out
    """

    __tablename__ = "agent_invocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Parent orchestrator that created this invocation
    parent_agent_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Target specialist (nullable — may be resolved asynchronously)
    child_agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    alert_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Parent orchestrator's assignment for this alert (nullable — orchestrator context)
    assignment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("alert_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Task specification
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    input_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="queued"
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cost tracking — cents incurred by the child agent for this invocation
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timeout enforcement
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)

    # Procrastinate job ID for status tracking
    task_queue_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    parent_agent: Mapped[AgentRegistration] = relationship(
        "AgentRegistration", foreign_keys=[parent_agent_id]
    )
    child_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[child_agent_id]
    )
    alert: Mapped[Alert] = relationship("Alert", foreign_keys=[alert_id])
    assignment: Mapped[AlertAssignment | None] = relationship(
        "AlertAssignment", foreign_keys=[assignment_id]
    )
