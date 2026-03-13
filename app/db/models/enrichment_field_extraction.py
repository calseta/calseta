"""EnrichmentFieldExtraction ORM model."""

from sqlalchemy import BigInteger, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class EnrichmentFieldExtraction(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "enrichment_field_extractions"
    __table_args__ = (
        UniqueConstraint(
            "provider_name", "indicator_type", "source_path",
            name="uq_enrichment_extraction_provider_type_path",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    indicator_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False, default="string")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text)
