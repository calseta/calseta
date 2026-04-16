"""HealthSource ORM model — configured cloud metric source (AWS, Azure, Calseta)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.health_metric_config import HealthMetricConfig


class HealthSource(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "health_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # "aws", "azure", "calseta"
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    auth_config_encrypted: Mapped[str | None] = mapped_column(Text)
    polling_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    last_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    last_poll_error: Mapped[str | None] = mapped_column(Text)

    # Relationships
    metric_configs: Mapped[list[HealthMetricConfig]] = relationship(
        "HealthMetricConfig",
        back_populates="health_source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<HealthSource id={self.id} name={self.name!r} provider={self.provider!r}>"
