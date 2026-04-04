"""KBPageLink ORM model — links from KB pages to other entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AppendOnlyTimestampMixin, Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.kb_page import KnowledgeBasePage


class KBPageLink(AppendOnlyTimestampMixin, UUIDMixin, Base):
    __tablename__ = "kb_page_links"

    __table_args__ = (
        UniqueConstraint(
            "page_id",
            "linked_entity_type",
            "linked_entity_id",
            name="uq_kb_page_links_page_entity",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_base_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    linked_entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    linked_entity_id: Mapped[object] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    link_type: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    page: Mapped[KnowledgeBasePage] = relationship("KnowledgeBasePage", back_populates="links")
