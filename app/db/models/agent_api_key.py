"""AgentAPIKey ORM model — scoped auth for agents calling back into Calseta."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if True:  # TYPE_CHECKING guard for forward refs
    from app.db.models.agent_registration import AgentRegistration


class AgentAPIKey(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_registration: Mapped[AgentRegistration] = relationship(
        "AgentRegistration",
        foreign_keys=[agent_registration_id],
        back_populates="api_keys",
    )
