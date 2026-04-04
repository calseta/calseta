"""AgentInstructionFile ORM model — instance-level instruction files for all managed agents."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AgentInstructionFile(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_instruction_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'global'"), default="global"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    inject_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
