"""UserValidationTemplate ORM model — Slack Block Kit message templates for user validation."""

from __future__ import annotations

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class UserValidationTemplate(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "user_validation_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(Text, nullable=False)
    confirm_label: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="Yes, that was me"
    )
    deny_label: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="No, that wasn't me"
    )
