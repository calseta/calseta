"""AgentIssueComment ORM model."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if True:
    from app.db.models.agent_issue import AgentIssue
    from app.db.models.agent_registration import AgentRegistration


class AgentIssueComment(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "agent_issue_comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_issues.id", ondelete="CASCADE"), nullable=False
    )
    author_agent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_registrations.id", ondelete="SET NULL"), nullable=True
    )
    author_operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    issue: Mapped[AgentIssue] = relationship("AgentIssue", back_populates="comments")
    author_agent: Mapped[AgentRegistration | None] = relationship(
        "AgentRegistration", foreign_keys=[author_agent_id]
    )
