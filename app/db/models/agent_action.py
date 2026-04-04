"""AgentAction ORM model — actions proposed or executed by agents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.alert_assignment import AlertAssignment


class AgentAction(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alert_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_subtype: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    approval_request_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("workflow_approval_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assignment: Mapped[AlertAssignment] = relationship(
        "AlertAssignment", foreign_keys=[assignment_id]
    )
    agent_registration: Mapped[AgentRegistration] = relationship(
        "AgentRegistration", foreign_keys=[agent_registration_id]
    )
