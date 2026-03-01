"""Alert ORM model — one row per security alert."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.detection_rule import DetectionRule


class Alert(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Normalized CalsetaAlert fields
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="Pending")
    severity_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Ingestion metadata
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fingerprint: Mapped[str | None] = mapped_column(Text)

    # Status lifecycle
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending_enrichment"
    )
    close_classification: Mapped[str | None] = mapped_column(Text)

    # Write-once lifecycle timestamps (set by service layer on status transitions)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Payload and tags
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    agent_findings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )

    # Foreign keys
    detection_rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("detection_rules.id", ondelete="SET NULL"),
    )

    # Relationships
    detection_rule: Mapped[DetectionRule | None] = relationship(
        "DetectionRule", foreign_keys=[detection_rule_id]
    )
