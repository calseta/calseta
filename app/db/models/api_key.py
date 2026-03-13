"""APIKey ORM model — authentication credentials."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class APIKey(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allowed_sources: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    key_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="human", server_default=text("'human'")
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
