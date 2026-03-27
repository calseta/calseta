"""Enrichment Pipeline — single public interface for HTTP-based IOC enrichment.

Usage::

    from app.services.enrichment_pipeline import EnrichmentPipeline

    pipeline = EnrichmentPipeline(
        provider_name="virustotal",
        http_config=provider_row.http_config,
        malice_rules=provider_row.malice_rules,
        field_extractions=extraction_dicts,
    )
    result = await pipeline.run("8.8.8.8", "ip", decrypted_auth)

Internal components (engine, field_extractor, malice_evaluator, template_resolver)
are implementation details and are NOT part of the public API.
"""

from __future__ import annotations

from typing import Any

from app.schemas.enrichment import EnrichmentResult

from .engine import GenericHttpEnrichmentEngine

__all__ = ["EnrichmentPipeline"]


class EnrichmentPipeline:
    """Public facade for the enrichment pipeline.

    Wraps :class:`GenericHttpEnrichmentEngine` behind a stable interface.
    Consumers should depend on this class, not the engine directly.
    """

    def __init__(
        self,
        provider_name: str,
        http_config: dict[str, Any],
        malice_rules: dict[str, Any] | None,
        field_extractions: list[dict[str, Any]],
    ) -> None:
        self._engine = GenericHttpEnrichmentEngine(
            provider_name=provider_name,
            http_config=http_config,
            malice_rules=malice_rules,
            field_extractions=field_extractions,
        )

    async def run(
        self,
        indicator_value: str,
        indicator_type: str,
        auth_config: dict[str, Any],
        *,
        capture_debug: bool = False,
    ) -> EnrichmentResult:
        """Execute the enrichment pipeline for a single indicator.

        Never raises — errors are returned as ``EnrichmentResult`` with
        ``success=False``.

        Args:
            indicator_value: The IOC value (IP, domain, hash, etc.).
            indicator_type: The indicator type string (``ip``, ``domain``, etc.).
            auth_config: Decrypted provider auth configuration dict.
            capture_debug: If True, attach per-step debug info to the result.

        Returns:
            :class:`EnrichmentResult` with extracted fields, raw response,
            and malice verdict.
        """
        return await self._engine.execute(
            indicator_value,
            indicator_type,
            auth_config,
            capture_debug,
        )
