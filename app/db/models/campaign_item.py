"""CampaignItem ORM model — links alerts/issues/routines to campaigns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AppendOnlyTimestampMixin, Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.campaign import Campaign


class CampaignItem(AppendOnlyTimestampMixin, UUIDMixin, Base):
    __tablename__ = "campaign_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(Text, nullable=False)  # alert, issue, routine
    # Polymorphic FK — stored as UUID (the external-facing ID)
    item_uuid: Mapped[str] = mapped_column(Text, nullable=False)  # store UUID as text

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="items")
