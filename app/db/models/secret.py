"""Secret and SecretVersion ORM models — secrets management system."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Secret(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "secrets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="local_encrypted")
    # For env_var provider: the env var name. For local_encrypted: null (stored in versions).
    env_var_name: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )

    versions: Mapped[list[SecretVersion]] = relationship(
        "SecretVersion", back_populates="secret", cascade="all, delete-orphan"
    )


class SecretVersion(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "secret_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    secret_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    encrypted_value: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    secret: Mapped[Secret] = relationship(
        "Secret", foreign_keys=[secret_id], back_populates="versions"
    )
