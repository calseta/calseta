"""ContextDocument ORM model — runbooks, IR plans, SOPs."""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ContextDocument(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "context_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    targeting_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
