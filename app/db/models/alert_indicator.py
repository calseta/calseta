"""AlertIndicator join model — many-to-many between alerts and indicators."""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AlertIndicator(TimestampMixin, Base):
    """
    No uuid column — this is a join table. created_at serves as the
    association timestamp. No updated_at (joins are never updated, only created or deleted).
    """

    __tablename__ = "alert_indicators"
    __table_args__ = (
        UniqueConstraint("alert_id", "indicator_id", name="uq_alert_indicator"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    indicator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("indicators.id", ondelete="CASCADE"), nullable=False
    )
