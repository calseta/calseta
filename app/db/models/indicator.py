"""Indicator ORM model — global entity, one row per unique (type, value) pair."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Indicator(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "indicators"
    __table_args__ = (UniqueConstraint("type", "value", name="uq_indicator_type_value"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    malice: Mapped[str] = mapped_column(Text, nullable=False, default="Pending")
    enrichment_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
