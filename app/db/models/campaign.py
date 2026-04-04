"""Campaign ORM model — strategic objectives grouping alerts, issues, and routines."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.campaign_item import CampaignItem


class Campaign(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="custom")
    owner_agent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_registrations.id", ondelete="SET NULL"), nullable=True
    )
    owner_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[owner_agent_id]
    )
    items: Mapped[list[CampaignItem]] = relationship(
        "CampaignItem", back_populates="campaign", cascade="all, delete-orphan"
    )
