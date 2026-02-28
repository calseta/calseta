"""AgentRegistration ORM model — registered agent webhook endpoints."""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AgentRegistration(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_registrations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_header_name: Mapped[str | None] = mapped_column(Text)
    auth_header_value_encrypted: Mapped[str | None] = mapped_column(Text)
    trigger_on_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="ARRAY[]::text[]"
    )
    trigger_on_severities: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="ARRAY[]::text[]"
    )
    trigger_filter: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    documentation: Mapped[str | None] = mapped_column(Text)
