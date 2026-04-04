"""CostEvent ORM model — token and cost tracking per agent interaction."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CostEvent(TimestampMixin, Base):
    __tablename__ = "cost_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_integration_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("llm_integrations.id", ondelete="SET NULL"),
    )
    alert_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("alerts.id", ondelete="SET NULL"),
    )
    heartbeat_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("heartbeat_runs.id", ondelete="SET NULL"),
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billing_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'api'"), default="api"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # No updated_at - CostEvent is append-only
