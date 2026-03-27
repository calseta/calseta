"""Backward-compatible re-export — real implementation in enrichment_pipeline.field_extractor.

This file will be removed in Chunk 1.4 after all consumers are migrated.
"""

from app.services.enrichment_pipeline.field_extractor import FieldExtractor  # noqa: F401

__all__ = ["FieldExtractor"]
