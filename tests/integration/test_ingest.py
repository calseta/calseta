"""Integration tests for alert ingestion — /v1/ingest and /v1/alerts (POST)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from tests.integration.conftest import auth_header

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestWebhookIngest:
    """POST /v1/ingest/{source_name}."""

    async def test_generic_webhook_202(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "Webhook Test",
                "severity": "Medium",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202

    async def test_webhook_returns_alert_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "UUID Test",
                "severity": "Low",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "alert_uuid" in data

    async def test_webhook_enqueues_task(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "Queue Test",
                "severity": "High",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(api_key),
        )
        mock_queue.enqueue.assert_called()

    async def test_unknown_source_404(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/ingest/nonexistent_source",
            json={"title": "test"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestGenericProgrammaticIngest:
    """POST /v1/alerts — generic programmatic ingest."""

    async def test_generic_ingest_202(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/alerts",
            json={
                "source_name": "generic",
                "payload": {
                    "title": "Programmatic Test",
                    "severity": "Low",
                    "occurred_at": "2026-01-15T10:00:00Z",
                },
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202

    async def test_generic_ingest_unknown_source_404(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/alerts",
            json={
                "source_name": "does_not_exist",
                "payload": {"title": "test"},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestSourceRestriction:
    """API key allowed_sources enforcement."""

    async def test_restricted_key_blocked(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
        mock_queue: AsyncMock,
    ) -> None:
        key = await scoped_api_key(["alerts:write"], allowed_sources=["sentinel"])
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "Restricted Test",
                "severity": "Low",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(key),
        )
        assert resp.status_code == 403

    async def test_restricted_key_allowed(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
        mock_queue: AsyncMock,
    ) -> None:
        key = await scoped_api_key(["alerts:write"], allowed_sources=["generic"])
        resp = await test_client.post(
            "/v1/ingest/generic",
            json={
                "title": "Allowed Test",
                "severity": "Low",
                "occurred_at": "2026-01-15T10:00:00Z",
            },
            headers=auth_header(key),
        )
        assert resp.status_code == 202


class TestSentinelIngest:
    """Sentinel webhook ingest with fixture payload."""

    async def test_sentinel_ingest_202(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        payload = json.loads((FIXTURES_DIR / "sentinel_alert.json").read_text())
        resp = await test_client.post(
            "/v1/ingest/sentinel",
            json=payload,
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202
