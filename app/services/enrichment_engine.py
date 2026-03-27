"""Backward-compatible re-export — real implementation in enrichment_pipeline.engine.

This file will be removed in Chunk 1.4 after all consumers are migrated.
"""

from app.services.enrichment_pipeline.engine import (  # noqa: F401
    GenericHttpEnrichmentEngine,
    mask_auth_values_in_url,
    mask_sensitive_headers,
)

__all__ = [
    "GenericHttpEnrichmentEngine",
    "mask_sensitive_headers",
    "mask_auth_values_in_url",
]
