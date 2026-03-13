"""SourceIntegration ORM model — configured alert sources."""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class SourceIntegration(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "source_integrations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_type: Mapped[str | None] = mapped_column(Text)
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    documentation: Mapped[str | None] = mapped_column(Text)
