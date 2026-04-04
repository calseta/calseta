"""AgentTool ORM model — tool registry for the agent tool system."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AgentTool(TimestampMixin, Base):
    """Tool registry — every tool available to managed agents."""

    __tablename__ = "agent_tools"

    # Tool ID is a text identifier, not a serial PK (e.g. "get_alert", "block_ip")
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    documentation: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    handler_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    # No uuid or BigInteger PK — use text id directly
