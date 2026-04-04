"""KnowledgeBasePage ORM model — KB and memory pages for agent context injection."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.kb_page_link import KBPageLink
    from app.db.models.kb_page_revision import KBPageRevision


class KnowledgeBasePage(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "knowledge_base_pages"

    __table_args__ = (
        Index("ix_kb_pages_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_kb_pages_folder", "folder"),
        Index("ix_kb_pages_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    folder: Mapped[str] = mapped_column(Text, nullable=False, default="/")
    format: Mapped[str] = mapped_column(Text, nullable=False, default="markdown")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="published")

    inject_scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    inject_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inject_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sync_source: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sync_last_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_operator: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NOTE: NOT a FK to kb_page_revisions to avoid circular dependency at migration time.
    latest_revision_id: Mapped[Any | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    latest_revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    search_vector: Mapped[Any | None] = mapped_column(
        "search_vector",
        TSVECTOR,
        nullable=True,
    )

    # Relationships
    created_by_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[created_by_agent_id]
    )
    updated_by_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[updated_by_agent_id]
    )
    revisions: Mapped[list[KBPageRevision]] = relationship(
        "KBPageRevision",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    links: Mapped[list[KBPageLink]] = relationship(
        "KBPageLink",
        back_populates="page",
        cascade="all, delete-orphan",
    )
