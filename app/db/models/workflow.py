"""Workflow ORM model — Python automation functions."""

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Workflow(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_type: Mapped[str | None] = mapped_column(Text)
    indicator_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    time_saved_minutes: Mapped[int | None] = mapped_column(Integer)
    approval_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="always", server_default="always"
    )
    approval_channel: Mapped[str | None] = mapped_column(Text)
    approval_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600
    )
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    documentation: Mapped[str | None] = mapped_column(Text)
