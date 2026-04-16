"""HealthMetric ORM model — time-series datapoints collected from health sources."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.health_metric_config import HealthMetricConfig


class HealthMetric(Base):
    """Time-series metric datapoint. No UUID or updated_at — append-only, high-volume."""

    __tablename__ = "health_metrics"
    __table_args__ = (
        Index(
            "ix_health_metrics_config_id_timestamp",
            "metric_config_id",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_config_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("health_metrics_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    raw_datapoints: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Relationships
    metric_config: Mapped[HealthMetricConfig] = relationship(
        "HealthMetricConfig",
        back_populates="metrics",
    )

    def __repr__(self) -> str:
        return (
            f"<HealthMetric id={self.id} config_id={self.metric_config_id} "
            f"value={self.value} ts={self.timestamp}>"
        )
