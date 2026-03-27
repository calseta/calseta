"""
End-to-end pipeline test: ingest -> enrich -> dispatch.

Exercises the full alert lifecycle by:
  1. Ingesting an Elastic alert via the HTTP endpoint
  2. Running the EnrichAlertHandler directly (simulating worker)
  3. Running the DispatchWebhooksHandler directly (simulating worker)

All external HTTP calls (enrichment providers, agent webhooks) are mocked.
Uses the real test database — no mocked repositories.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.db.models.alert_indicator import AlertIndicator
from app.db.models.indicator import Indicator
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.queue.handlers.dispatch_webhooks import DispatchWebhooksHandler
from app.queue.handlers.enrich_alert import EnrichAlertHandler
from app.queue.handlers.payloads import (
    DispatchAgentWebhooksPayload,
    EnrichAlertPayload,
)
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType
from tests.integration.conftest import auth_header

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_queue() -> AsyncGenerator[AsyncMock, None]:
    """Mock task queue for ingest endpoint (prevents real enqueue calls)."""
    from app.main import app
    from app.queue.dependencies import get_queue

    mock = AsyncMock()
    mock.enqueue.return_value = "mock-task-id"
    app.dependency_overrides[get_queue] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_queue, None)


@pytest_asyncio.fixture
async def registered_agent(db_session: AsyncSession) -> AgentRegistration:
    """Create a registered agent that triggers on elastic + High severity."""
    agent = AgentRegistration(
        uuid=uuid.uuid4(),
        name="e2e-test-agent",
        description="Agent for E2E pipeline test",
        endpoint_url="https://agent.example.com/webhook",
        trigger_on_sources=["elastic"],
        trigger_on_severities=["High"],
        trigger_filter=None,
        timeout_seconds=10,
        retry_count=0,
        is_active=True,
    )
    db_session.add(agent)
    await db_session.flush()
    return agent


def _make_mock_provider(
    name: str,
    supported_types: list[IndicatorType],
    malice: str = "Malicious",
) -> EnrichmentProviderBase:
    """Create a mock enrichment provider that returns a canned result."""
    provider = MagicMock(spec=EnrichmentProviderBase)
    provider.provider_name = name
    provider.supported_types = set(supported_types)
    provider.is_configured.return_value = True
    provider.get_cache_ttl.return_value = 300

    async def _enrich(value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        return EnrichmentResult(
            provider_name=name,
            success=True,
            status="success",
            extracted={"malice": malice, "score": 85},
            raw={"full_response": "mocked"},
        )

    provider.enrich = AsyncMock(side_effect=_enrich)
    return provider


# ---------------------------------------------------------------------------
# E2E Pipeline Test
# ---------------------------------------------------------------------------


class TestIngestEnrichDispatchPipeline:
    """Full pipeline: ingest -> enrich -> dispatch with real DB, mocked HTTP."""

    async def test_full_pipeline(
        self,
        test_client: AsyncClient,
        api_key: str,
        db_session: AsyncSession,
        mock_queue: AsyncMock,
        registered_agent: AgentRegistration,
    ) -> None:
        """
        Exercise the complete ingest -> enrich -> dispatch pipeline.

        Verifies:
          - Alert is created with correct fields
          - Indicators are extracted from the Elastic payload
          - Enrichment results are persisted on indicators
          - Malice verdicts are set
          - Alert enrichment_status transitions to Enriched
          - Agent webhook dispatch is called with the correct payload
        """
        # ---------------------------------------------------------------
        # Stage 1: INGEST — POST an Elastic alert
        # ---------------------------------------------------------------
        elastic_payload = json.loads(
            (FIXTURES_DIR / "elastic_alert.json").read_text()
        )

        resp = await test_client.post(
            "/v1/ingest/elastic",
            json=elastic_payload,
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202, f"Ingest failed: {resp.text}"
        ingest_data = resp.json()["data"]
        assert ingest_data["is_duplicate"] is False
        alert_uuid = ingest_data["alert_uuid"]

        # Verify the alert exists in DB
        result = await db_session.execute(
            select(Alert).where(Alert.uuid == uuid.UUID(alert_uuid))
        )
        alert = result.scalar_one()
        assert alert.source_name == "elastic"
        assert alert.severity == "High"
        assert alert.title == "Suspicious PowerShell Execution"
        assert alert.enrichment_status == "Pending"
        assert alert.raw_payload is not None

        # Verify enrich_alert task was enqueued
        mock_queue.enqueue.assert_called()
        enqueue_call = mock_queue.enqueue.call_args
        assert enqueue_call[0][0] == "enrich_alert"
        assert enqueue_call[0][1]["alert_id"] == alert.id

        # ---------------------------------------------------------------
        # Stage 2: ENRICH — run the handler directly
        # ---------------------------------------------------------------
        # Set up a mock enrichment provider for IPs
        mock_vt = _make_mock_provider(
            "virustotal",
            [IndicatorType.IP, IndicatorType.DOMAIN, IndicatorType.HASH_SHA256],
            malice="Malicious",
        )

        # Patch the enrichment registry to return our mock provider
        with patch(
            "app.services.enrichment.enrichment_registry"
        ) as mock_registry:
            mock_registry.list_for_type.return_value = [mock_vt]

            handler = EnrichAlertHandler()
            payload = EnrichAlertPayload(alert_id=alert.id)
            await handler.execute(payload, db_session)

        # Verify indicators were extracted and persisted
        indicator_links = await db_session.execute(
            select(AlertIndicator).where(AlertIndicator.alert_id == alert.id)
        )
        link_rows = list(indicator_links.scalars().all())
        assert len(link_rows) > 0, "No indicators were linked to the alert"

        # Load indicators and verify enrichment
        indicator_ids = [link.indicator_id for link in link_rows]
        indicators_result = await db_session.execute(
            select(Indicator).where(Indicator.id.in_(indicator_ids))
        )
        indicators = list(indicators_result.scalars().all())
        assert len(indicators) > 0

        # Check that at least one indicator was enriched
        enriched_indicators = [ind for ind in indicators if ind.is_enriched]
        assert len(enriched_indicators) > 0, "No indicators were enriched"

        # Verify malice verdict was set on enriched indicators.
        # Private IPs (e.g. 10.0.0.55) are skipped by is_enrichable() and
        # may still be marked is_enriched=True at the alert level but retain
        # malice="Pending" — only check indicators that were actually enriched
        # by a provider (have enrichment_results).
        provider_enriched = [
            ind
            for ind in enriched_indicators
            if ind.enrichment_results and "virustotal" in ind.enrichment_results
        ]
        assert len(provider_enriched) > 0, "No indicators were enriched by a provider"
        for ind in provider_enriched:
            assert ind.malice == "Malicious", (
                f"Expected Malicious, got {ind.malice} for {ind.type}:{ind.value}"
            )

        # Verify alert enrichment status was updated
        await db_session.refresh(alert)
        assert alert.enrichment_status == "Enriched"
        assert alert.is_enriched is True

        # Verify specific indicator types were extracted from the fixture
        indicator_types = {ind.type for ind in indicators}
        # The Elastic fixture has: source.ip, destination.ip, host.ip,
        # destination.domain, dns.question.name, url.full,
        # process.hash.sha256, process.hash.md5, user.email, user.name
        assert "ip" in indicator_types, f"Expected ip indicators, got {indicator_types}"
        assert "domain" in indicator_types, f"Expected domain indicators, got {indicator_types}"

        # ---------------------------------------------------------------
        # Stage 3: DISPATCH — run the webhook handler directly
        # ---------------------------------------------------------------
        # Mock the outbound HTTP call to the agent webhook endpoint
        with patch(
            "app.services.agent_dispatch.httpx.AsyncClient"
        ) as mock_http_class:
            # Set up the mock HTTP client
            mock_http_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.json.return_value = {"status": "received"}
            mock_response.text = '{"status": "received"}'
            mock_http_client.post.return_value = mock_response
            mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client.__aexit__ = AsyncMock(return_value=False)
            mock_http_class.return_value = mock_http_client

            # Also patch SSRF validation to allow our test URL
            with patch(
                "app.services.agent_dispatch.validate_outbound_url"
            ):
                dispatch_handler = DispatchWebhooksHandler()
                dispatch_payload = DispatchAgentWebhooksPayload(alert_id=alert.id)
                await dispatch_handler.execute(dispatch_payload, db_session)

            # Verify the webhook was called
            mock_http_client.post.assert_called_once()
            call_args = mock_http_client.post.call_args

            # Verify the webhook URL matches the agent's endpoint
            assert call_args[0][0] == "https://agent.example.com/webhook"

            # Verify the webhook payload contains the alert data
            webhook_body = call_args[1]["json"]
            assert "alert" in webhook_body
            assert webhook_body["alert"]["uuid"] == alert_uuid
            assert webhook_body["alert"]["title"] == "Suspicious PowerShell Execution"
            assert webhook_body["alert"]["severity"] == "High"
            assert webhook_body["alert"]["source_name"] == "elastic"

            # Verify indicators are included in the webhook payload
            assert "indicators" in webhook_body
            assert len(webhook_body["indicators"]) > 0

            # Verify at least one indicator has enrichment results
            enriched_in_payload = [
                ind
                for ind in webhook_body["indicators"]
                if ind.get("enrichment_results")
            ]
            assert len(enriched_in_payload) > 0, (
                "Webhook payload should include enriched indicators"
            )

    async def test_pipeline_no_matching_agents(
        self,
        test_client: AsyncClient,
        api_key: str,
        db_session: AsyncSession,
        mock_queue: AsyncMock,
    ) -> None:
        """
        When no agents match the alert, dispatch completes without errors
        and no webhook calls are made.
        """
        # Ingest a generic alert (no agents registered for generic source)
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "No Agent Test",
                "severity": "Low",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202
        alert_uuid = resp.json()["data"]["alert_uuid"]

        result = await db_session.execute(
            select(Alert).where(Alert.uuid == uuid.UUID(alert_uuid))
        )
        alert = result.scalar_one()

        # Run dispatch — should return silently (no agents match)
        with patch(
            "app.services.agent_dispatch.httpx.AsyncClient"
        ) as mock_http_class:
            mock_http_client = AsyncMock()
            mock_http_class.return_value = mock_http_client

            dispatch_handler = DispatchWebhooksHandler()
            dispatch_payload = DispatchAgentWebhooksPayload(alert_id=alert.id)
            await dispatch_handler.execute(dispatch_payload, db_session)

            # No HTTP calls should have been made
            mock_http_client.post.assert_not_called()

    async def test_enrichment_with_no_indicators(
        self,
        test_client: AsyncClient,
        api_key: str,
        db_session: AsyncSession,
        mock_queue: AsyncMock,
    ) -> None:
        """
        When an alert has no extractable indicators, enrichment still
        completes and marks the alert as Enriched.
        """
        # Ingest a minimal generic alert (no IOCs in payload)
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "Minimal Alert",
                "severity": "Informational",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202
        alert_uuid = resp.json()["data"]["alert_uuid"]

        result = await db_session.execute(
            select(Alert).where(Alert.uuid == uuid.UUID(alert_uuid))
        )
        alert = result.scalar_one()

        # Run enrichment — no indicators to enrich
        handler = EnrichAlertHandler()
        payload = EnrichAlertPayload(alert_id=alert.id)
        await handler.execute(payload, db_session)

        # Alert should still be marked as enriched
        await db_session.refresh(alert)
        assert alert.enrichment_status == "Enriched"
        assert alert.is_enriched is True
