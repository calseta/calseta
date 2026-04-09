"""AgentRegistration ORM model — registered agent webhook endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.agent_api_key import AgentAPIKey


class AgentRegistration(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_registrations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # --- Existing fields (webhook dispatch) ---
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    auth_header_name: Mapped[str | None] = mapped_column(Text)
    auth_header_value_encrypted: Mapped[str | None] = mapped_column(Text)
    trigger_on_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    trigger_on_severities: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    trigger_filter: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    documentation: Mapped[str | None] = mapped_column(Text)

    # --- Control plane: replaces is_active ---
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'"), default="active"
    )

    # --- Control plane: identity & type ---
    execution_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'external'"), default="external"
    )
    agent_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'standalone'"), default="standalone"
    )
    role: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # --- Control plane: adapter ---
    adapter_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'webhook'"), default="webhook"
    )
    adapter_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # --- Control plane: managed agent config ---
    llm_integration_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("llm_integrations.id", ondelete="SET NULL"),
    )
    system_prompt: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str | None] = mapped_column(Text)
    tool_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    enable_thinking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    instruction_files: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    # --- Control plane: orchestrator config ---
    sub_agent_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    max_sub_agent_calls: Mapped[int | None] = mapped_column(Integer)

    # --- Control plane: budget ---
    budget_monthly_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    spent_monthly_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    budget_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Control plane: runtime ---
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent_alerts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )
    max_cost_per_alert_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    max_investigation_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    stall_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    memory_promotion_requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # --- Relationships ---
    api_keys: Mapped[list[AgentAPIKey]] = relationship(
        "AgentAPIKey", back_populates="agent_registration", cascade="all, delete-orphan"
    )
