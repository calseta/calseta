"""SkillFile ORM model — individual files within a skill's directory tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.skill import Skill


class SkillFile(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "skill_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_entry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    skill: Mapped[Skill] = relationship("Skill", back_populates="files")
