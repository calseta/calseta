"""WorkflowApprovalRequest ORM model — human-in-the-loop approval lifecycle."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class WorkflowApprovalRequest(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "workflow_approval_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workflow_runs.id", ondelete="SET NULL")
    )
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_agent_key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    notifier_type: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    notifier_channel: Mapped[str | None] = mapped_column(Text)
    external_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    responder_id: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decide_token: Mapped[str | None] = mapped_column(Text)
