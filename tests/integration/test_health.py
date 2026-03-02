"""Integration tests for GET /health — no auth required."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealth:
    async def test_health_returns_200(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert resp.status_code == 200

    async def test_health_response_keys(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        body = resp.json()
        assert "status" in body
        assert "db" in body
        assert "queue_depth" in body
        assert "enrichment_providers" in body

    async def test_health_no_auth_required(self, test_client: AsyncClient) -> None:
        """Health endpoint must work without any Authorization header."""
        resp = await test_client.get("/health")
        # Health endpoint returns 200 (ok) or 503 (down) — never 401/403
        assert resp.status_code in (200, 503)
        assert resp.status_code not in (401, 403)
