"""LLMIntegration ORM model — instance-level LLM provider configurations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class LLMIntegration(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "llm_integrations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_ref: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_per_1k_input_tokens_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_per_1k_output_tokens_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
