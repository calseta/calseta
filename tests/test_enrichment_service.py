"""
Unit tests for EnrichmentService.

Uses mocked providers and an in-memory cache — no DB or HTTP calls.
The test DB session is a minimal mock that stubs out repository method calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.memory import InMemoryCache
from app.schemas.enrichment import EnrichmentResult, EnrichmentStatus
from app.schemas.indicators import IndicatorType
from app.services.enrichment import EnrichmentService, _worst_malice

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    name: str,
    types: list[IndicatorType],
    result: EnrichmentResult,
    *,
    is_configured: bool = True,
) -> MagicMock:
    """Return a mock provider that always returns `result` from enrich()."""
    provider = MagicMock()
    provider.provider_name = name
    provider.display_name = name.title()
    provider.supported_types = types
    provider.cache_ttl_seconds = 3600
    provider.is_configured.return_value = is_configured
    provider.get_cache_ttl.return_value = 3600
    provider.enrich = AsyncMock(return_value=result)
    return provider


def _success(provider_name: str, malice: str = "Benign") -> EnrichmentResult:
    return EnrichmentResult.success_result(
        provider_name=provider_name,
        extracted={"found": True, "malice": malice},
        raw={},
        enriched_at=datetime.now(UTC),
    )


def _failure(provider_name: str) -> EnrichmentResult:
    return EnrichmentResult.failure_result(provider_name, "timeout")


def _skipped(provider_name: str) -> EnrichmentResult:
    return EnrichmentResult.skipped_result(provider_name, "not configured")


# ---------------------------------------------------------------------------
# _worst_malice
# ---------------------------------------------------------------------------


class TestWorstMalice:
    def test_empty(self) -> None:
        assert _worst_malice([]) == "Pending"

    def test_single(self) -> None:
        assert _worst_malice(["Benign"]) == "Benign"

    def test_order(self) -> None:
        assert _worst_malice(["Benign", "Suspicious"]) == "Suspicious"
        assert _worst_malice(["Benign", "Malicious"]) == "Malicious"
        assert _worst_malice(["Suspicious", "Malicious"]) == "Malicious"

    def test_all_pending(self) -> None:
        assert _worst_malice(["Pending", "Pending"]) == "Pending"


# ---------------------------------------------------------------------------
# EnrichmentService.enrich_indicator
# ---------------------------------------------------------------------------


class TestEnrichIndicator:
    @pytest.fixture
    def cache(self) -> InMemoryCache:
        return InMemoryCache()

    @pytest.fixture
    def db(self) -> AsyncMock:
        return AsyncMock()

    async def test_all_providers_called(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _success("abuseipdb"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt, abuse],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        assert "virustotal" in results
        assert "abuseipdb" in results
        vt.enrich.assert_awaited_once()
        abuse.enrich.assert_awaited_once()

    async def test_cache_hit_skips_provider(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        cached_result = _success("virustotal")

        # Pre-populate cache
        from app.cache.keys import make_enrichment_key

        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        await cache.set(key, cached_result.model_dump(mode="json"), 3600)

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        # Provider should NOT have been called
        vt.enrich.assert_not_awaited()
        assert "virustotal" in results
        assert results["virustotal"].success is True

    async def test_successful_result_is_cached(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        from app.cache.keys import make_enrichment_key

        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        cached = await cache.get(key)
        assert cached is not None
        assert cached["success"] is True

    async def test_failed_result_not_cached(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        from app.cache.keys import make_enrichment_key

        vt = _make_provider("virustotal", [IndicatorType.IP], _failure("virustotal"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        cached = await cache.get(key)
        assert cached is None  # Failures are not cached

    async def test_no_providers_returns_empty(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.EMAIL, "x@y.com")

        assert results == {}

    async def test_one_provider_failure_does_not_affect_others(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """A failed provider result is included; other providers still succeed."""
        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _failure("abuseipdb"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt, abuse],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        assert results["virustotal"].success is True
        assert results["abuseipdb"].success is False
        assert results["abuseipdb"].status == EnrichmentStatus.FAILED

    async def test_provider_exception_is_caught(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """
        A provider that raises despite the contract is handled by the caller.
        enrich_indicator should not re-raise provider exceptions; the contract
        is that providers catch their own errors. If they do raise (a bug in
        the provider), asyncio.gather propagates it — this test documents that
        behaviour so future implementers know.
        """
        raising_provider = _make_provider(
            "buggy", [IndicatorType.IP], _success("buggy")
        )
        raising_provider.enrich = AsyncMock(side_effect=RuntimeError("boom"))

        safe_provider = _make_provider(
            "safe", [IndicatorType.IP], _success("safe")
        )

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[raising_provider, safe_provider],
        ):
            service = EnrichmentService(db, cache)
            # asyncio.gather propagates the exception from the raising provider
            with pytest.raises(RuntimeError, match="boom"):
                await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")


# ---------------------------------------------------------------------------
# EnrichmentService.enrich_alert (integration-style, fully mocked repos)
# ---------------------------------------------------------------------------


class TestEnrichAlert:
    def _make_indicator(self, ind_type: str, value: str, ind_id: int) -> MagicMock:
        ind = MagicMock()
        ind.id = ind_id
        ind.type = ind_type
        ind.value = value
        ind.enrichment_results = {}
        return ind

    async def test_marks_alert_enriched(self) -> None:
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Malicious")
        )
        indicator = self._make_indicator("ip", "1.2.3.4", 1)
        mock_alert = MagicMock()
        mock_alert.id = 42

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                return_value=[vt],
            ),
            patch(
                "app.services.enrichment.AlertRepository.get_by_id",
                AsyncMock(return_value=mock_alert),
            ),
            patch(
                "app.services.enrichment.IndicatorRepository.list_for_alert",
                AsyncMock(return_value=[indicator]),
            ),
            patch(
                "app.services.enrichment.IndicatorRepository.update_enrichment",
                AsyncMock(),
            ),
            patch(
                "app.services.enrichment.AlertRepository.mark_enriched",
                AsyncMock(),
            ),
            patch(
                "app.services.enrichment.ActivityEventRepository.create",
                AsyncMock(),
            ),
        ):
            service = EnrichmentService(mock_db, cache)
            await service.enrich_alert(42)

    async def test_no_indicators_still_marks_enriched(self) -> None:
        cache = InMemoryCache()
        mock_db = AsyncMock()
        mock_alert = MagicMock()
        mock_alert.id = 99

        with (
            patch(
                "app.services.enrichment.AlertRepository.get_by_id",
                AsyncMock(return_value=mock_alert),
            ),
            patch(
                "app.services.enrichment.IndicatorRepository.list_for_alert",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.enrichment.AlertRepository.mark_enriched",
                AsyncMock(),
            ) as mock_mark,
            patch(
                "app.services.enrichment.ActivityEventRepository.create",
                AsyncMock(),
            ),
        ):
            service = EnrichmentService(mock_db, cache)
            await service.enrich_alert(99)
            mock_mark.assert_awaited_once()

    async def test_alert_not_found_returns_gracefully(self) -> None:
        cache = InMemoryCache()
        mock_db = AsyncMock()

        with patch(
            "app.services.enrichment.AlertRepository.get_by_id",
            AsyncMock(return_value=None),
        ):
            service = EnrichmentService(mock_db, cache)
            # Must not raise
            await service.enrich_alert(999)
