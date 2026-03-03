"""EnrichmentProvider ORM model — database-driven enrichment provider configuration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class EnrichmentProvider(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "enrichment_providers"
    __table_args__ = (
        UniqueConstraint("provider_name", name="uq_enrichment_provider_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supported_indicator_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    http_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    auth_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="no_auth"
    )
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    env_var_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    default_cache_ttl_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600
    )
    cache_ttl_by_type: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    malice_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mock_responses: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
