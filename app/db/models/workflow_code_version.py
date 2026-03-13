"""WorkflowCodeVersion ORM model — version history for workflow code edits."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkflowCodeVersion(Base):
    __tablename__ = "workflow_code_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
