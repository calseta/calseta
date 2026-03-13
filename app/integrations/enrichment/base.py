"""
EnrichmentProviderBase — abstract interface for all enrichment providers.

All providers must follow these contracts:
  - `enrich()` MUST NEVER RAISE. Catch all exceptions and return
    EnrichmentResult.failure_result(...). This is non-negotiable.
  - `is_configured()` checks that required env vars are set.
  - `supported_types` lists which IndicatorTypes this provider handles.

Cache TTL policy:
  - Default TTLs by type: IP=3600, Domain=21600, Hash=86400, URL=1800, Account=900
  - Providers may override per-type TTL via `_TTL_BY_TYPE` class var.
  - Cache key format: `enrichment:{provider_name}:{type}:{value}`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

# Default TTL in seconds by indicator type (PRD Section 7.2)
DEFAULT_TTL_BY_TYPE: dict[IndicatorType, int] = {
    IndicatorType.IP: 3600,
    IndicatorType.DOMAIN: 21600,
    IndicatorType.HASH_MD5: 86400,
    IndicatorType.HASH_SHA1: 86400,
    IndicatorType.HASH_SHA256: 86400,
    IndicatorType.URL: 1800,
    IndicatorType.EMAIL: 3600,
    IndicatorType.ACCOUNT: 900,
}


class EnrichmentProviderBase(ABC):
    """
    Abstract enrichment provider.

    Subclass and implement `enrich()` and `is_configured()`.
    All providers are registered via `enrichment_registry.register(MyProvider())`.

    Contract:
        enrich() must never raise — all exceptions must be caught and returned
        as EnrichmentResult.failure_result(self.provider_name, str(e)).
    """

    provider_name: str
    display_name: str
    supported_types: list[IndicatorType]
    cache_ttl_seconds: int = 3600  # Default; per-type TTLs preferred

    # Per-provider TTL overrides by type. If not set, falls back to DEFAULT_TTL_BY_TYPE.
    _TTL_BY_TYPE: dict[IndicatorType, int] = {}

    @abstractmethod
    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Enrich the given indicator value.

        Must never raise. Catch all exceptions and return:
            EnrichmentResult.failure_result(self.provider_name, str(e))

        Args:
            value:          The indicator value (e.g. "1.2.3.4", "evil.com").
            indicator_type: The IndicatorType of the value.

        Returns:
            EnrichmentResult — always, even on failure.
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Return True if all required environment variables are set.

        Called by the registry's list_configured() to filter ready providers.
        Never raises — returns False on any error.
        """

    def get_cache_ttl(self, indicator_type: IndicatorType) -> int:
        """Return the cache TTL in seconds for the given indicator type."""
        merged = {**DEFAULT_TTL_BY_TYPE, **self._TTL_BY_TYPE}
        return merged.get(indicator_type, self.cache_ttl_seconds)
