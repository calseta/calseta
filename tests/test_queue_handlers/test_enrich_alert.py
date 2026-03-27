"""Unit tests for EnrichAlertHandler.

Tests the enrich_alert task handler with mocked dependencies:
- AlertRepository (get_by_id, mark_enrichment_failed)
- source_registry (get)
- IndicatorExtractionService (extract_and_persist)
- EnrichmentService (enrich_alert)
- get_cache_backend
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.queue.handlers.enrich_alert import EnrichAlertHandler
from app.queue.handlers.payloads import EnrichAlertPayload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> EnrichAlertHandler:
    return EnrichAlertHandler()


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_alert() -> MagicMock:
    alert = MagicMock()
    alert.source_name = "elastic"
    alert.raw_payload = {"event": {"kind": "alert"}, "message": "test"}
    return alert


@pytest.fixture
def mock_source() -> MagicMock:
    source = MagicMock()
    source.normalize.return_value = MagicMock()
    return source


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestEnrichAlertHappyPath:
    @pytest.mark.asyncio
    async def test_extracts_indicators_and_enriches(
        self,
        handler: EnrichAlertHandler,
        session: AsyncMock,
        mock_alert: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """Full pipeline: alert found -> indicators extracted -> enrichment succeeds."""
        payload = EnrichAlertPayload(alert_id=42)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        mock_extraction_svc = MagicMock()
        mock_extraction_svc.extract_and_persist = AsyncMock(return_value=3)

        mock_enrichment_svc = MagicMock()
        mock_enrichment_svc.enrich_alert = AsyncMock()

        mock_cache = MagicMock()

        with (
            patch(
                "app.queue.handlers.enrich_alert.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.enrich_alert.source_registry"
            ) as mock_registry,
            patch(
                "app.queue.handlers.enrich_alert.IndicatorExtractionService",
                return_value=mock_extraction_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.EnrichmentService",
                return_value=mock_enrichment_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.get_cache_backend",
                return_value=mock_cache,
            ),
        ):
            mock_registry.get.return_value = mock_source
            await handler.execute(payload, session)

        # Verify indicator extraction was called
        mock_extraction_svc.extract_and_persist.assert_awaited_once()

        # Verify enrichment was called
        mock_enrichment_svc.enrich_alert.assert_awaited_once_with(42)

        # Verify session.flush was called (after extraction)
        session.flush.assert_awaited()


# ---------------------------------------------------------------------------
# Alert not found
# ---------------------------------------------------------------------------


class TestEnrichAlertNotFound:
    @pytest.mark.asyncio
    async def test_returns_gracefully_when_alert_missing(
        self,
        handler: EnrichAlertHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns without raising when alert_id doesn't exist."""
        payload = EnrichAlertPayload(alert_id=999)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=None)

        with patch(
            "app.queue.handlers.enrich_alert.AlertRepository",
            return_value=mock_alert_repo,
        ):
            # Should not raise
            await handler.execute(payload, session)

        mock_alert_repo.get_by_id.assert_awaited_once_with(999)


# ---------------------------------------------------------------------------
# Extraction failure
# ---------------------------------------------------------------------------


class TestEnrichAlertExtractionFailure:
    @pytest.mark.asyncio
    async def test_continues_to_enrichment_after_extraction_error(
        self,
        handler: EnrichAlertHandler,
        session: AsyncMock,
        mock_alert: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """If indicator extraction raises, handler logs and continues to enrichment."""
        payload = EnrichAlertPayload(alert_id=10)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        mock_extraction_svc = MagicMock()
        mock_extraction_svc.extract_and_persist = AsyncMock(
            side_effect=RuntimeError("extraction boom")
        )

        mock_enrichment_svc = MagicMock()
        mock_enrichment_svc.enrich_alert = AsyncMock()

        mock_cache = MagicMock()

        with (
            patch(
                "app.queue.handlers.enrich_alert.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.enrich_alert.source_registry"
            ) as mock_registry,
            patch(
                "app.queue.handlers.enrich_alert.IndicatorExtractionService",
                return_value=mock_extraction_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.EnrichmentService",
                return_value=mock_enrichment_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.get_cache_backend",
                return_value=mock_cache,
            ),
        ):
            mock_registry.get.return_value = mock_source
            # Should not raise despite extraction failure
            await handler.execute(payload, session)

        # Enrichment should still be called after extraction failure
        mock_enrichment_svc.enrich_alert.assert_awaited_once_with(10)


# ---------------------------------------------------------------------------
# Enrichment failure -> marks alert as Failed
# ---------------------------------------------------------------------------


class TestEnrichAlertEnrichmentFailure:
    @pytest.mark.asyncio
    async def test_marks_enrichment_failed_on_error(
        self,
        handler: EnrichAlertHandler,
        session: AsyncMock,
        mock_alert: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """If enrichment raises, handler marks alert enrichment_status as Failed."""
        payload = EnrichAlertPayload(alert_id=7)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)
        mock_alert_repo.mark_enrichment_failed = AsyncMock()

        mock_extraction_svc = MagicMock()
        mock_extraction_svc.extract_and_persist = AsyncMock(return_value=1)

        mock_enrichment_svc = MagicMock()
        mock_enrichment_svc.enrich_alert = AsyncMock(
            side_effect=RuntimeError("enrichment boom")
        )

        mock_cache = MagicMock()

        with (
            patch(
                "app.queue.handlers.enrich_alert.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.enrich_alert.source_registry"
            ) as mock_registry,
            patch(
                "app.queue.handlers.enrich_alert.IndicatorExtractionService",
                return_value=mock_extraction_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.EnrichmentService",
                return_value=mock_enrichment_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.get_cache_backend",
                return_value=mock_cache,
            ),
        ):
            mock_registry.get.return_value = mock_source
            # Should not raise
            await handler.execute(payload, session)

        # Should have attempted to mark enrichment as failed
        mock_alert_repo.mark_enrichment_failed.assert_awaited_once_with(mock_alert)

    @pytest.mark.asyncio
    async def test_no_source_plugin_still_runs_enrichment(
        self,
        handler: EnrichAlertHandler,
        session: AsyncMock,
        mock_alert: MagicMock,
    ) -> None:
        """If source plugin not found, extraction is skipped but enrichment runs."""
        payload = EnrichAlertPayload(alert_id=5)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        mock_enrichment_svc = MagicMock()
        mock_enrichment_svc.enrich_alert = AsyncMock()

        mock_cache = MagicMock()

        with (
            patch(
                "app.queue.handlers.enrich_alert.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.enrich_alert.source_registry"
            ) as mock_registry,
            patch(
                "app.queue.handlers.enrich_alert.EnrichmentService",
                return_value=mock_enrichment_svc,
            ),
            patch(
                "app.queue.handlers.enrich_alert.get_cache_backend",
                return_value=mock_cache,
            ),
        ):
            mock_registry.get.return_value = None  # No source plugin
            await handler.execute(payload, session)

        # Enrichment should still run
        mock_enrichment_svc.enrich_alert.assert_awaited_once_with(5)
