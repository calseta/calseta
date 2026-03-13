"""IndicatorFieldMapping ORM model — indicator extraction field mappings."""

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class IndicatorFieldMapping(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "indicator_field_mappings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_name: Mapped[str | None] = mapped_column(Text)  # NULL = global/system
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    indicator_type: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_target: Mapped[str] = mapped_column(
        Text, nullable=False, default="normalized"
    )  # "normalized" | "raw_payload"
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text)
