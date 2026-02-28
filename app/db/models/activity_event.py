"""ActivityEvent ORM model — immutable append-only audit log."""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AppendOnlyTimestampMixin, Base, UUIDMixin


class ActivityEvent(AppendOnlyTimestampMixin, UUIDMixin, Base):
    """
    Append-only. No updated_at. Records are never modified after creation.
    created_at is the event timestamp.
    """

    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)  # system | api | mcp
    actor_key_prefix: Mapped[str | None] = mapped_column(Text)

    # Polymorphic FK — at most one will be set per event
    alert_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="SET NULL")
    )
    workflow_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workflows.id", ondelete="SET NULL")
    )
    detection_rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("detection_rules.id", ondelete="SET NULL")
    )
    references: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
