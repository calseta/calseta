"""KBPageRevision ORM model — immutable revision history for KB pages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AppendOnlyTimestampMixin, Base, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.kb_page import KnowledgeBasePage


class KBPageRevision(AppendOnlyTimestampMixin, UUIDMixin, Base):
    __tablename__ = "kb_page_revisions"

    __table_args__ = (
        UniqueConstraint("page_id", "revision_number", name="uq_kb_page_revisions_page_revision"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_base_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    author_agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    page: Mapped[KnowledgeBasePage] = relationship("KnowledgeBasePage", back_populates="revisions")
    author_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[author_agent_id]
    )
