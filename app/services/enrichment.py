"""
EnrichmentService — async parallel enrichment pipeline.

Used by:
- enrich_alert_task (worker): processes all indicators for a given alert
- POST /v1/enrichments: on-demand synchronous enrichment for a single indicator

Design:
    For alert enrichment, all indicators are processed concurrently via
    asyncio.gather(). Within each indicator, all applicable providers run
    concurrently. Cache is checked before each provider call; successful
    results are cached for their provider-defined TTL.

Malice aggregation:
    Malicious(3) > Suspicious(2) > Benign(1) > Pending(0)
    If no provider returns a malice field in its extracted data, the
    indicator stays at "Pending".

Error isolation:
    Each provider's enrich() is already exception-safe (never raises per the
    base contract). The outer gather catches any unforeseen exception from a
    single indicator's pipeline without failing the rest.
"""

from __future__ import annotations

import asyncio
import ipaddress
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.base import CacheBackendBase
from app.cache.keys import make_enrichment_key
from app.integrations.enrichment.registry import enrichment_registry
from app.repositories.activity_event_repository import ActivityEventRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.activity_events import ActivityEventType
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Indicator enrichability validation — pure functions
#
# Determines whether an indicator value is worth sending to external enrichment
# providers. Non-routable IPs (RFC 1918, loopback, link-local, CGNAT, etc.) and
# internal domains (.local, .internal, etc.) are skipped to avoid fabricated
# verdicts from threat intel APIs that don't handle private addresses correctly.
#
# Indicators are still persisted regardless — only external API enrichment is skipped.
# ---------------------------------------------------------------------------

_NON_ROUTABLE_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".home",
    ".lan",
    ".corp",
    ".test",
    ".example",
    ".invalid",
    ".arpa",
)

_NON_ROUTABLE_EXACT: frozenset[str] = frozenset({"localhost"})


def is_enrichable(indicator_type: IndicatorType, value: str) -> tuple[bool, str | None]:
    """
    Check whether an indicator should be sent to external enrichment providers.

    Returns (True, None) if enrichable, or (False, reason) if it should be skipped.
    """
    if indicator_type == IndicatorType.IP:
        return _is_ip_enrichable(value)
    if indicator_type == IndicatorType.DOMAIN:
        return _is_domain_enrichable(value)
    if indicator_type == IndicatorType.URL:
        return _is_url_enrichable(value)
    # Hash, email, account — always enrichable
    return True, None


def _is_ip_enrichable(value: str) -> tuple[bool, str | None]:
    """Return (False, reason) for non-global IPs (private, loopback, link-local, etc.)."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False, "invalid IP address format"

    if not addr.is_global:
        return False, f"non-routable IP address ({value})"
    return True, None


def _is_domain_enrichable(value: str) -> tuple[bool, str | None]:
    """Return (False, reason) for internal/reserved domain suffixes."""
    lower = value.lower().rstrip(".")
    if lower in _NON_ROUTABLE_EXACT:
        return False, f"reserved domain ({value})"
    for suffix in _NON_ROUTABLE_SUFFIXES:
        if lower == suffix.lstrip(".") or lower.endswith(suffix):
            return False, f"non-routable domain suffix ({value})"
    return True, None


def _is_url_enrichable(value: str) -> tuple[bool, str | None]:
    """Extract hostname from URL and delegate to IP or domain validator."""
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except Exception:
        return False, "invalid URL format"

    if not hostname:
        return False, "URL has no hostname"

    # Check if hostname is an IP address
    try:
        ipaddress.ip_address(hostname)
        return _is_ip_enrichable(hostname)
    except ValueError:
        pass

    return _is_domain_enrichable(hostname)


# ---------------------------------------------------------------------------
# Malice aggregation
# ---------------------------------------------------------------------------

_MALICE_PRIORITY: dict[str, int] = {
    "Pending": 0,
    "Benign": 1,
    "Suspicious": 2,
    "Malicious": 3,
}


def _worst_malice(verdicts: list[str]) -> str:
    """Return highest-priority malice verdict from a list, or 'Pending' if empty."""
    if not verdicts:
        return "Pending"
    return max(verdicts, key=lambda v: _MALICE_PRIORITY.get(v, 0))


class EnrichmentService:
    def __init__(self, db: AsyncSession, cache: CacheBackendBase) -> None:
        self._db = db
        self._cache = cache
        self._alert_repo = AlertRepository(db)
        self._indicator_repo = IndicatorRepository(db)
        self._activity_repo = ActivityEventRepository(db)

    async def enrich_indicator(
        self,
        indicator_type: IndicatorType,
        value: str,
    ) -> dict[str, EnrichmentResult]:
        """
        Run all configured providers for a single indicator (cache-first).

        Returns dict of provider_name → EnrichmentResult.
        Never raises — provider failures are captured in results.
        """
        enrichable, skip_reason = is_enrichable(indicator_type, value)
        if not enrichable:
            logger.info(
                "enrichment_skipped_not_enrichable",
                indicator_type=str(indicator_type),
                value=value[:64],
                reason=skip_reason,
            )
            return {
                "_validation": EnrichmentResult.skipped_result(
                    provider_name="_validation",
                    reason=f"Enrichment skipped: {skip_reason}",
                )
            }

        providers = enrichment_registry.list_for_type(indicator_type)
        if not providers:
            return {}

        results: dict[str, EnrichmentResult] = {}
        uncached_providers = []

        for provider in providers:
            cache_key = make_enrichment_key(
                provider.provider_name, str(indicator_type), value
            )
            cached = await self._cache.get(cache_key)
            if cached is not None:
                results[provider.provider_name] = EnrichmentResult.model_validate(cached)
                logger.debug(
                    "enrichment_cache_hit",
                    provider=provider.provider_name,
                    indicator_type=str(indicator_type),
                    value=value[:64],
                )
            else:
                uncached_providers.append(provider)

        if uncached_providers:
            live_results: list[EnrichmentResult] = await asyncio.gather(
                *[p.enrich(value, indicator_type) for p in uncached_providers],
            )
            for provider, result in zip(uncached_providers, live_results, strict=True):
                if result.success:
                    ttl = provider.get_cache_ttl(indicator_type)
                    cache_key = make_enrichment_key(
                        provider.provider_name, str(indicator_type), value
                    )
                    await self._cache.set(cache_key, result.model_dump(mode="json"), ttl)
                results[provider.provider_name] = result

        return results

    async def enrich_alert(self, alert_id: int) -> None:
        """
        Run the full enrichment pipeline for all indicators of an alert.

        Steps:
          1. Load all indicators for the alert.
          2. Run enrich_indicator() for each indicator concurrently.
          3. Update indicator.enrichment_results, malice, is_enriched.
          4. Mark alert.is_enriched = True, status = enriched.
          5. Write alert_enrichment_completed activity event (fire-and-forget).

        Must never raise — catches and logs all errors.
        """
        alert = None
        try:
            alert = await self._alert_repo.get_by_id(alert_id)
            if alert is None:
                logger.error("enrich_alert_not_found", alert_id=alert_id)
                return

            indicators = await self._indicator_repo.list_for_alert(alert_id)

            if not indicators:
                logger.info("enrich_alert_no_indicators", alert_id=alert_id)
                await self._alert_repo.mark_enriched(alert)
                await self._write_enrichment_event(alert_id, 0, [], [], {})
                return

            # Enrich all indicators concurrently
            all_results: list[dict[str, EnrichmentResult]] = await asyncio.gather(
                *[
                    self.enrich_indicator(IndicatorType(ind.type), ind.value)
                    for ind in indicators
                ],
            )

            providers_succeeded: set[str] = set()
            providers_failed: set[str] = set()
            malice_counts: dict[str, int] = {
                "Pending": 0,
                "Benign": 0,
                "Suspicious": 0,
                "Malicious": 0,
            }

            for indicator, results in zip(indicators, all_results, strict=True):
                malice_verdicts = [
                    r.extracted["malice"]
                    for r in results.values()
                    if r.success and r.extracted and "malice" in r.extracted
                ]
                malice = _worst_malice(malice_verdicts)
                malice_counts[malice] = malice_counts.get(malice, 0) + 1

                enrichment_payload: dict[str, Any] = {
                    name: result.model_dump(mode="json")
                    for name, result in results.items()
                }
                await self._indicator_repo.update_enrichment(
                    indicator, malice, enrichment_payload
                )

                for name, result in results.items():
                    if result.success:
                        providers_succeeded.add(name)
                    elif result.status == "failed":
                        providers_failed.add(name)

            await self._alert_repo.mark_enriched(alert)

            await self._write_enrichment_event(
                alert_id=alert_id,
                indicator_count=len(indicators),
                providers_succeeded=sorted(providers_succeeded),
                providers_failed=sorted(providers_failed),
                malice_counts=malice_counts,
            )

            logger.info(
                "alert_enrichment_completed",
                alert_id=alert_id,
                indicator_count=len(indicators),
                providers_succeeded=sorted(providers_succeeded),
                providers_failed=sorted(providers_failed),
            )

        except Exception:
            logger.exception("enrich_alert_pipeline_failed", alert_id=alert_id)
            # Mark enrichment as failed so the alert doesn't stay stuck at Pending
            try:
                if alert is not None:
                    await self._alert_repo.mark_enrichment_failed(alert)
            except Exception:
                logger.exception(
                    "mark_enrichment_failed_error", alert_id=alert_id
                )

    async def _write_enrichment_event(
        self,
        alert_id: int,
        indicator_count: int,
        providers_succeeded: list[str],
        providers_failed: list[str],
        malice_counts: dict[str, int],
    ) -> None:
        """Write alert_enrichment_completed activity event. Swallows all errors."""
        try:
            await self._activity_repo.create(
                event_type=ActivityEventType.ALERT_ENRICHMENT_COMPLETED.value,
                actor_type="system",
                actor_key_prefix=None,
                alert_id=alert_id,
                references={
                    "indicator_count": indicator_count,
                    "providers_succeeded": providers_succeeded,
                    "providers_failed": providers_failed,
                    "malice_counts": malice_counts,
                    "enriched_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            logger.exception(
                "enrichment_activity_event_failed", alert_id=alert_id
            )
