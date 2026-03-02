"""
Pipeline orchestration tests for the enrichment engine.

Covers:
  1. Enrich 3 indicators concurrently — all complete
  2. One provider failure must not block others (isolation)
  3. Cache hit test — same indicator enriched twice, HTTP called only once
  4. Malice verdict aggregation — worst verdict wins (Malicious > Suspicious > Benign > Pending)
  5. enrich_alert full pipeline (mocked repos)
  6. Edge cases: empty providers, no indicators, alert not found

Uses mocked providers, in-memory cache, and mocked repositories — no DB or HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.keys import make_enrichment_key
from app.cache.memory import InMemoryCache
from app.schemas.enrichment import EnrichmentResult, EnrichmentStatus
from app.schemas.indicators import IndicatorType
from app.services.enrichment import EnrichmentService, _MALICE_PRIORITY, _worst_malice


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
        raw={"provider": provider_name},
        enriched_at=datetime.now(UTC),
    )


def _failure(provider_name: str, error: str = "timeout") -> EnrichmentResult:
    return EnrichmentResult.failure_result(provider_name, error)


def _skipped(provider_name: str, reason: str = "not configured") -> EnrichmentResult:
    return EnrichmentResult.skipped_result(provider_name, reason)


def _make_indicator(ind_type: str, value: str, ind_id: int) -> MagicMock:
    """Create a mock indicator ORM object."""
    ind = MagicMock()
    ind.id = ind_id
    ind.type = ind_type
    ind.value = value
    ind.enrichment_results = {}
    return ind


# ===================================================================
# _worst_malice Tests
# ===================================================================


class TestWorstMalice:
    """Malice verdict aggregation logic."""

    def test_empty_list_returns_pending(self) -> None:
        assert _worst_malice([]) == "Pending"

    def test_single_benign(self) -> None:
        assert _worst_malice(["Benign"]) == "Benign"

    def test_single_suspicious(self) -> None:
        assert _worst_malice(["Suspicious"]) == "Suspicious"

    def test_single_malicious(self) -> None:
        assert _worst_malice(["Malicious"]) == "Malicious"

    def test_single_pending(self) -> None:
        assert _worst_malice(["Pending"]) == "Pending"

    def test_malicious_wins_over_all(self) -> None:
        assert _worst_malice(["Pending", "Benign", "Suspicious", "Malicious"]) == "Malicious"

    def test_suspicious_wins_over_benign_and_pending(self) -> None:
        assert _worst_malice(["Pending", "Benign", "Suspicious"]) == "Suspicious"

    def test_benign_wins_over_pending(self) -> None:
        assert _worst_malice(["Pending", "Benign"]) == "Benign"

    def test_all_pending(self) -> None:
        assert _worst_malice(["Pending", "Pending", "Pending"]) == "Pending"

    def test_all_malicious(self) -> None:
        assert _worst_malice(["Malicious", "Malicious"]) == "Malicious"

    def test_malice_priority_order(self) -> None:
        """Verify priority constants are correct."""
        assert _MALICE_PRIORITY["Pending"] < _MALICE_PRIORITY["Benign"]
        assert _MALICE_PRIORITY["Benign"] < _MALICE_PRIORITY["Suspicious"]
        assert _MALICE_PRIORITY["Suspicious"] < _MALICE_PRIORITY["Malicious"]

    def test_two_providers_benign_and_malicious(self) -> None:
        """Worst verdict of [Benign, Malicious] is Malicious."""
        assert _worst_malice(["Benign", "Malicious"]) == "Malicious"

    def test_two_providers_benign_and_suspicious(self) -> None:
        assert _worst_malice(["Benign", "Suspicious"]) == "Suspicious"

    def test_unknown_verdict_treated_as_pending(self) -> None:
        """Unknown malice strings default to priority 0 (same as Pending)."""
        # Unknown string should not win over known verdicts
        assert _worst_malice(["Benign", "UnknownStuff"]) == "Benign"


# ===================================================================
# EnrichmentService.enrich_indicator — Pipeline Tests
# ===================================================================


class TestEnrichIndicatorPipeline:
    @pytest.fixture
    def cache(self) -> InMemoryCache:
        return InMemoryCache()

    @pytest.fixture
    def db(self) -> AsyncMock:
        return AsyncMock()

    async def test_all_providers_called_concurrently(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """All configured providers for a type are called."""
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
        assert results["virustotal"].success is True
        assert results["abuseipdb"].success is True
        vt.enrich.assert_awaited_once()
        abuse.enrich.assert_awaited_once()

    async def test_three_indicators_concurrently_all_complete(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """Enrich 3 different indicator types concurrently — all complete."""
        vt_ip = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _success("abuseipdb"))
        vt_domain = _make_provider(
            "virustotal", [IndicatorType.DOMAIN], _success("virustotal")
        )
        okta = _make_provider("okta", [IndicatorType.ACCOUNT], _success("okta"))

        def _list_for_type(itype: IndicatorType) -> list[MagicMock]:
            if itype == IndicatorType.IP:
                return [vt_ip, abuse]
            if itype == IndicatorType.DOMAIN:
                return [vt_domain]
            if itype == IndicatorType.ACCOUNT:
                return [okta]
            return []

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            side_effect=_list_for_type,
        ):
            service = EnrichmentService(db, cache)

            ip_results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")
            domain_results = await service.enrich_indicator(
                IndicatorType.DOMAIN, "evil.com"
            )
            account_results = await service.enrich_indicator(
                IndicatorType.ACCOUNT, "alice@example.com"
            )

        assert len(ip_results) == 2
        assert len(domain_results) == 1
        assert len(account_results) == 1
        assert all(r.success for r in ip_results.values())
        assert all(r.success for r in domain_results.values())
        assert all(r.success for r in account_results.values())

    async def test_one_provider_failure_does_not_block_others(
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

    async def test_all_providers_fail_gracefully(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """All providers failing still returns complete dict with no raise."""
        vt = _make_provider("virustotal", [IndicatorType.IP], _failure("virustotal"))
        abuse = _make_provider(
            "abuseipdb", [IndicatorType.IP], _failure("abuseipdb", "network error")
        )

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt, abuse],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        assert len(results) == 2
        assert all(not r.success for r in results.values())

    async def test_cache_hit_skips_provider_call(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """Pre-populated cache result prevents provider.enrich() call."""
        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        cached_result = _success("virustotal")

        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        await cache.set(key, cached_result.model_dump(mode="json"), 3600)

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        # Provider should NOT have been called — cache hit
        vt.enrich.assert_not_awaited()
        assert "virustotal" in results
        assert results["virustotal"].success is True

    async def test_cache_miss_calls_provider_and_caches_result(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """On cache miss, provider is called and successful result is cached."""
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

    async def test_same_indicator_enriched_twice_uses_cache(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """Same indicator enriched twice — provider HTTP called only once."""
        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Malicious")
        )

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            # First call
            results1 = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")
            # Second call should be a cache hit
            results2 = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        # Provider called exactly once (first call only)
        assert vt.enrich.await_count == 1
        assert results1["virustotal"].success is True
        assert results2["virustotal"].success is True

    async def test_failed_result_not_cached(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """Failed enrichment results are NOT cached."""
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

    async def test_skipped_result_not_cached(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """Skipped enrichment results are NOT cached (success=False)."""
        vt = _make_provider("virustotal", [IndicatorType.IP], _skipped("virustotal"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt],
        ):
            service = EnrichmentService(db, cache)
            await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        cached = await cache.get(key)
        assert cached is None

    async def test_no_providers_returns_empty_dict(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.EMAIL, "x@y.com")

        assert results == {}

    async def test_mixed_cache_hit_and_miss(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """One provider cached, other not — only uncached provider is called."""
        vt = _make_provider("virustotal", [IndicatorType.IP], _success("virustotal"))
        abuse = _make_provider(
            "abuseipdb", [IndicatorType.IP], _success("abuseipdb", "Suspicious")
        )

        # Pre-populate only virustotal in cache
        vt_key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        await cache.set(
            vt_key, _success("virustotal").model_dump(mode="json"), 3600
        )

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[vt, abuse],
        ):
            service = EnrichmentService(db, cache)
            results = await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")

        vt.enrich.assert_not_awaited()  # cached
        abuse.enrich.assert_awaited_once()  # called live
        assert "virustotal" in results
        assert "abuseipdb" in results

    async def test_provider_bug_raising_exception(
        self, db: AsyncMock, cache: InMemoryCache
    ) -> None:
        """If a provider violates the contract and raises, asyncio.gather propagates it."""
        buggy = _make_provider("buggy", [IndicatorType.IP], _success("buggy"))
        buggy.enrich = AsyncMock(side_effect=RuntimeError("provider bug"))

        safe = _make_provider("safe", [IndicatorType.IP], _success("safe"))

        with patch(
            "app.services.enrichment.enrichment_registry.list_for_type",
            return_value=[buggy, safe],
        ):
            service = EnrichmentService(db, cache)
            with pytest.raises(RuntimeError, match="provider bug"):
                await service.enrich_indicator(IndicatorType.IP, "1.2.3.4")


# ===================================================================
# EnrichmentService.enrich_alert — Full Pipeline Tests
# ===================================================================


class TestEnrichAlertPipeline:
    """Test the enrich_alert method with fully mocked repositories."""

    async def test_marks_alert_enriched_after_success(self) -> None:
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Malicious")
        )
        indicator = _make_indicator("ip", "1.2.3.4", 1)
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
            ) as mock_update,
            patch(
                "app.services.enrichment.AlertRepository.mark_enriched",
                AsyncMock(),
            ) as mock_mark,
            patch(
                "app.services.enrichment.ActivityEventRepository.create",
                AsyncMock(),
            ) as mock_activity,
        ):
            service = EnrichmentService(mock_db, cache)
            await service.enrich_alert(42)

            mock_mark.assert_awaited_once()
            mock_update.assert_awaited_once()
            mock_activity.assert_awaited_once()

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

    async def test_multiple_indicators_enriched_concurrently(self) -> None:
        """Multiple indicators are enriched concurrently with correct malice aggregation."""
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt_malicious = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Malicious")
        )
        abuse_suspicious = _make_provider(
            "abuseipdb", [IndicatorType.IP], _success("abuseipdb", "Suspicious")
        )

        ip_indicator = _make_indicator("ip", "1.2.3.4", 1)
        domain_indicator = _make_indicator("domain", "evil.com", 2)
        account_indicator = _make_indicator("account", "alice@example.com", 3)

        mock_alert = MagicMock()
        mock_alert.id = 10

        update_calls: list[tuple[MagicMock, str, dict]] = []

        async def _mock_update(indicator: MagicMock, malice: str, results: dict) -> None:
            update_calls.append((indicator, malice, results))

        def _list_for_type(itype: IndicatorType) -> list[MagicMock]:
            if itype == IndicatorType.IP:
                return [vt_malicious, abuse_suspicious]
            return []  # No providers for domain/account

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                side_effect=_list_for_type,
            ),
            patch(
                "app.services.enrichment.AlertRepository.get_by_id",
                AsyncMock(return_value=mock_alert),
            ),
            patch(
                "app.services.enrichment.IndicatorRepository.list_for_alert",
                AsyncMock(
                    return_value=[ip_indicator, domain_indicator, account_indicator]
                ),
            ),
            patch(
                "app.services.enrichment.IndicatorRepository.update_enrichment",
                AsyncMock(side_effect=_mock_update),
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
            await service.enrich_alert(10)

        # 3 indicators should have been updated
        assert len(update_calls) == 3

        # The IP indicator should have the worst verdict from VT (Malicious) and Abuse (Suspicious)
        ip_call = [c for c in update_calls if c[0].value == "1.2.3.4"][0]
        assert ip_call[1] == "Malicious"  # Worst of [Malicious, Suspicious]

        # Domain and account indicators have no providers, so malice stays Pending
        domain_call = [c for c in update_calls if c[0].value == "evil.com"][0]
        assert domain_call[1] == "Pending"

    async def test_activity_event_written_with_correct_references(self) -> None:
        """Verify the activity event references contain correct provider info."""
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Malicious")
        )
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _failure("abuseipdb"))
        indicator = _make_indicator("ip", "1.2.3.4", 1)
        mock_alert = MagicMock()
        mock_alert.id = 42

        activity_calls: list[dict] = []

        async def _capture_activity(**kwargs: object) -> None:
            activity_calls.append(dict(kwargs))

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                return_value=[vt, abuse],
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
                AsyncMock(side_effect=_capture_activity),
            ),
        ):
            service = EnrichmentService(mock_db, cache)
            await service.enrich_alert(42)

        assert len(activity_calls) == 1
        refs = activity_calls[0]["references"]
        assert refs["indicator_count"] == 1
        assert "virustotal" in refs["providers_succeeded"]
        assert "abuseipdb" in refs["providers_failed"]
        assert "malice_counts" in refs
        assert refs["malice_counts"]["Malicious"] == 1

    async def test_pipeline_exception_logged_not_raised(self) -> None:
        """If an unexpected exception occurs in enrich_alert, it's caught and logged."""
        cache = InMemoryCache()
        mock_db = AsyncMock()

        with patch(
            "app.services.enrichment.AlertRepository.get_by_id",
            AsyncMock(side_effect=RuntimeError("DB connection lost")),
        ):
            service = EnrichmentService(mock_db, cache)
            # Must not raise
            await service.enrich_alert(42)

    async def test_activity_event_failure_does_not_propagate(self) -> None:
        """If writing the activity event fails, enrichment still completes."""
        cache = InMemoryCache()
        mock_db = AsyncMock()
        mock_alert = MagicMock()
        mock_alert.id = 42

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
                AsyncMock(side_effect=RuntimeError("activity write failed")),
            ),
        ):
            service = EnrichmentService(mock_db, cache)
            # Must not raise even though activity event fails
            await service.enrich_alert(42)
            mock_mark.assert_awaited_once()


# ===================================================================
# Malice Aggregation Integration Tests
# ===================================================================


class TestMaliceAggregation:
    """End-to-end malice verdict aggregation in the enrichment pipeline."""

    async def test_malicious_wins_over_suspicious(self) -> None:
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Suspicious")
        )
        abuse = _make_provider(
            "abuseipdb", [IndicatorType.IP], _success("abuseipdb", "Malicious")
        )
        indicator = _make_indicator("ip", "1.2.3.4", 1)
        mock_alert = MagicMock()
        mock_alert.id = 1

        update_calls: list[tuple[MagicMock, str, dict]] = []

        async def _capture_update(
            indicator: MagicMock, malice: str, results: dict
        ) -> None:
            update_calls.append((indicator, malice, results))

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                return_value=[vt, abuse],
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
                AsyncMock(side_effect=_capture_update),
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
            await service.enrich_alert(1)

        assert len(update_calls) == 1
        assert update_calls[0][1] == "Malicious"

    async def test_failed_provider_excluded_from_malice_aggregation(self) -> None:
        """Failed provider results don't contribute to malice verdict."""
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider(
            "virustotal", [IndicatorType.IP], _success("virustotal", "Benign")
        )
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _failure("abuseipdb"))
        indicator = _make_indicator("ip", "1.2.3.4", 1)
        mock_alert = MagicMock()
        mock_alert.id = 1

        update_calls: list[tuple[MagicMock, str, dict]] = []

        async def _capture_update(
            indicator: MagicMock, malice: str, results: dict
        ) -> None:
            update_calls.append((indicator, malice, results))

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                return_value=[vt, abuse],
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
                AsyncMock(side_effect=_capture_update),
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
            await service.enrich_alert(1)

        assert len(update_calls) == 1
        # Only VT succeeded with Benign — AbuseIPDB failure is excluded
        assert update_calls[0][1] == "Benign"

    async def test_no_successful_providers_keeps_pending(self) -> None:
        """If all providers fail, malice stays Pending."""
        cache = InMemoryCache()
        mock_db = AsyncMock()

        vt = _make_provider("virustotal", [IndicatorType.IP], _failure("virustotal"))
        abuse = _make_provider("abuseipdb", [IndicatorType.IP], _failure("abuseipdb"))
        indicator = _make_indicator("ip", "1.2.3.4", 1)
        mock_alert = MagicMock()
        mock_alert.id = 1

        update_calls: list[tuple[MagicMock, str, dict]] = []

        async def _capture_update(
            indicator: MagicMock, malice: str, results: dict
        ) -> None:
            update_calls.append((indicator, malice, results))

        with (
            patch(
                "app.services.enrichment.enrichment_registry.list_for_type",
                return_value=[vt, abuse],
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
                AsyncMock(side_effect=_capture_update),
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
            await service.enrich_alert(1)

        assert update_calls[0][1] == "Pending"


# ===================================================================
# Registry Tests
# ===================================================================


class TestEnrichmentRegistry:
    """Tests for the enrichment registry behavior."""

    def test_register_and_get(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        provider = _make_provider("test_provider", [IndicatorType.IP], _success("test"))
        registry.register(provider)
        assert registry.get("test_provider") is provider

    def test_get_unknown_returns_none(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        assert registry.get("nonexistent") is None

    def test_duplicate_registration_raises(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        p1 = _make_provider("dup", [IndicatorType.IP], _success("dup"))
        p2 = _make_provider("dup", [IndicatorType.IP], _success("dup"))
        registry.register(p1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(p2)

    def test_list_all(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        p1 = _make_provider("a", [IndicatorType.IP], _success("a"), is_configured=True)
        p2 = _make_provider("b", [IndicatorType.IP], _success("b"), is_configured=False)
        registry.register(p1)
        registry.register(p2)
        assert len(registry.list_all()) == 2

    def test_list_configured_filters_unconfigured(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        p1 = _make_provider("configured", [IndicatorType.IP], _success("a"), is_configured=True)
        p2 = _make_provider("unconfigured", [IndicatorType.IP], _success("b"), is_configured=False)
        registry.register(p1)
        registry.register(p2)
        configured = registry.list_configured()
        assert len(configured) == 1
        assert configured[0].provider_name == "configured"

    def test_list_for_type_filters_by_type_and_configured(self) -> None:
        from app.integrations.enrichment.registry import EnrichmentRegistry

        registry = EnrichmentRegistry()
        p_ip = _make_provider("ip_only", [IndicatorType.IP], _success("a"), is_configured=True)
        p_domain = _make_provider(
            "domain_only", [IndicatorType.DOMAIN], _success("b"), is_configured=True
        )
        p_unconfigured = _make_provider(
            "unconfigured_ip", [IndicatorType.IP], _success("c"), is_configured=False
        )
        registry.register(p_ip)
        registry.register(p_domain)
        registry.register(p_unconfigured)

        ip_providers = registry.list_for_type(IndicatorType.IP)
        assert len(ip_providers) == 1
        assert ip_providers[0].provider_name == "ip_only"

        domain_providers = registry.list_for_type(IndicatorType.DOMAIN)
        assert len(domain_providers) == 1
        assert domain_providers[0].provider_name == "domain_only"

        email_providers = registry.list_for_type(IndicatorType.EMAIL)
        assert len(email_providers) == 0


# ===================================================================
# Cache Key Tests
# ===================================================================


class TestCacheKeys:
    def test_make_enrichment_key_format(self) -> None:
        key = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        assert key == "enrichment:virustotal:ip:1.2.3.4"

    def test_different_values_produce_different_keys(self) -> None:
        k1 = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        k2 = make_enrichment_key("virustotal", "ip", "5.6.7.8")
        assert k1 != k2

    def test_different_providers_produce_different_keys(self) -> None:
        k1 = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        k2 = make_enrichment_key("abuseipdb", "ip", "1.2.3.4")
        assert k1 != k2

    def test_different_types_produce_different_keys(self) -> None:
        k1 = make_enrichment_key("virustotal", "ip", "1.2.3.4")
        k2 = make_enrichment_key("virustotal", "domain", "1.2.3.4")
        assert k1 != k2
