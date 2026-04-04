"""UserValidationRule ORM model — rules that trigger user validation actions on alerts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class UserValidationRule(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "user_validation_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("user_validation_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_field_path: Mapped[str] = mapped_column(Text, nullable=False)
    timeout_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    on_confirm: Mapped[str] = mapped_column(Text, nullable=False, default="close_alert")
    on_deny: Mapped[str] = mapped_column(Text, nullable=False, default="escalate_alert")
    on_timeout: Mapped[str] = mapped_column(Text, nullable=False, default="escalate_alert")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
