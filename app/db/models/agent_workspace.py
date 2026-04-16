"""AgentWorkspace ORM model — workspace for detection-as-code agent work."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AgentWorkspace(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_workspaces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_registration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'generic'"), default="generic"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'"), default="active"
    )
    directory_path: Mapped[str | None] = mapped_column(Text)
    git_remote_url: Mapped[str | None] = mapped_column(Text)
    git_branch: Mapped[str | None] = mapped_column(Text)
    git_last_commit_sha: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    def __repr__(self) -> str:
        return (
            f"<AgentWorkspace id={self.id} type={self.workspace_type!r} "
            f"status={self.status!r}>"
        )
