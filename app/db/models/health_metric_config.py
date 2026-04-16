"""HealthMetricConfig ORM model — what to poll from a health source."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.health_metric import HealthMetric
    from app.db.models.health_source import HealthSource


class HealthMetricConfig(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "health_metrics_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    health_source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("health_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    namespace: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    statistic: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Average'")
    )
    unit: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'None'")
    )
    category: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'custom'")
    )
    card_size: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'wide'")
    )
    warning_threshold: Mapped[float | None] = mapped_column(Float)
    critical_threshold: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    # Relationships
    health_source: Mapped[HealthSource] = relationship(
        "HealthSource",
        back_populates="metric_configs",
    )
    metrics: Mapped[list[HealthMetric]] = relationship(
        "HealthMetric",
        back_populates="metric_config",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<HealthMetricConfig id={self.id} "
            f"display_name={self.display_name!r} metric={self.metric_name!r}>"
        )
