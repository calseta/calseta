"""Backward-compatible re-export — real implementation in enrichment_pipeline.template_resolver.

This file will be removed in Chunk 1.4 after all consumers are migrated.
"""

from app.services.enrichment_pipeline.template_resolver import TemplateResolver  # noqa: F401

__all__ = ["TemplateResolver"]
