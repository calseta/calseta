"""AgentRun ORM model — webhook delivery audit log."""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AgentRun(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)
