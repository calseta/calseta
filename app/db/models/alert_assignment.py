"""AlertAssignment ORM model — atomic checkout table for agent work queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if True:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.alert import Alert


class AlertAssignment(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "alert_assignments"

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
    status: Mapped[str] = mapped_column(Text, nullable=False, default="assigned")
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    resolution_type: Mapped[str | None] = mapped_column(Text)
    investigation_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    alert: Mapped[Alert] = relationship(
        "Alert", foreign_keys=[alert_id]
    )
    agent_registration: Mapped[AgentRegistration] = relationship(
        "AgentRegistration", foreign_keys=[agent_registration_id]
    )
