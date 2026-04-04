"""AgentIssue ORM model — non-alert work items for agents and operators."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_issue_comment import AgentIssueComment
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.alert import Alert
    from app.db.models.heartbeat_run import HeartbeatRun


class AgentIssue(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_issues.id", ondelete="SET NULL"), nullable=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    routine_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="investigation")
    assignee_agent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_registrations.id", ondelete="SET NULL"), nullable=True
    )
    assignee_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_registrations.id", ondelete="SET NULL"), nullable=True
    )
    created_by_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("heartbeat_runs.id", ondelete="SET NULL"), nullable=True
    )
    execution_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    alert: Mapped[Alert | None] = relationship("Alert", foreign_keys=[alert_id])
    assignee_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[assignee_agent_id]
    )
    created_by_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[created_by_agent_id]
    )
    checkout_run: Mapped[HeartbeatRun | None] = relationship(
        "HeartbeatRun", foreign_keys=[checkout_run_id]
    )
    comments: Mapped[list[AgentIssueComment]] = relationship(
        "AgentIssueComment", back_populates="issue", cascade="all, delete-orphan"
    )
