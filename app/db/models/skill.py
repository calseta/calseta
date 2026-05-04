"""Skill ORM model — skill bundles (directory model) assigned to agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.skill_file import SkillFile


class Skill(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 'manual' (operator-edited; loader will not touch) or 'bundled' (managed
    # by the universal startup loader from ``app/skills/<slug>/``).
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="manual", server_default="manual"
    )
    # SHA256 over the concatenated file contents of the bundled skill — used by
    # the loader to skip re-writing SkillFile rows when nothing changed on disk.
    # Always NULL for source='manual' rows.
    content_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)

    files: Mapped[list[SkillFile]] = relationship(
        "SkillFile",
        back_populates="skill",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SkillFile.path",
    )
