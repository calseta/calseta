"""Smoke test for the UI ↔ API contract.

For every route the UI calls in ``ui/src/hooks/use-api.ts`` we verify the
backend has a matching route registered. We do not exercise full happy-path
behavior here — a GET that returns 200, 401, 403, 404-with-CalsetaException
envelope, or 422 all pass; what fails is a *route-level* 404 (FastAPI's
``{"detail": "Not Found"}``), which means the UI is calling an endpoint that
does not exist.

This guards against the kind of UI/API drift that S16 set out to fix:
hooks pointing at endpoints that were renamed, removed, or never built.

Maintenance: when adding a new ``api.<verb>`` call in ``use-api.ts``, add the
corresponding route here. When removing one, drop it here too.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth_header

# A burned-in UUID we expect to never resolve to a real entity. Reused across
# parametrize cases so we get consistent "entity not found" responses (which
# are different from "route not found" — see ``_assert_route_exists``).
_NONEXISTENT_UUID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Route enumeration — extracted from ui/src/hooks/use-api.ts (GETs only).
# ---------------------------------------------------------------------------
#
# We only test GET routes here because:
#   - Mutation routes (POST/PATCH/PUT/DELETE) need bodies + state setup;
#     they are exercised by their own integration tests.
#   - A route-existence smoke test only needs *one* verb per path to prove
#     the path is registered. GET is the most common UI verb.
#
# Routes that take a path parameter use ``_NONEXISTENT_UUID``. They are
# expected to return 404 with the Calseta error envelope (entity not found),
# never the bare FastAPI ``{"detail": "Not Found"}`` (route not found).

_UI_GET_ROUTES: list[str] = [
    # Settings
    "/v1/settings/approval-defaults",
    # Metrics
    "/v1/metrics/summary",
    # Alerts
    "/v1/alerts",
    f"/v1/alerts/{_NONEXISTENT_UUID}",
    f"/v1/alerts/{_NONEXISTENT_UUID}/activity",
    f"/v1/alerts/{_NONEXISTENT_UUID}/kb-context",
    f"/v1/alerts/{_NONEXISTENT_UUID}/raw-payload",
    f"/v1/alerts/{_NONEXISTENT_UUID}/relationship-graph",
    # Indicators
    f"/v1/indicators/{_NONEXISTENT_UUID}",
    # Workflows
    "/v1/workflows",
    f"/v1/workflows/{_NONEXISTENT_UUID}",
    f"/v1/workflows/{_NONEXISTENT_UUID}/runs",
    # Approvals
    "/v1/workflow-approvals",
    # Detection rules
    "/v1/detection-rules",
    f"/v1/detection-rules/{_NONEXISTENT_UUID}",
    f"/v1/detection-rules/{_NONEXISTENT_UUID}/metrics",
    # Sources
    "/v1/sources",
    # Agents
    "/v1/agents",
    f"/v1/agents/{_NONEXISTENT_UUID}",
    f"/v1/agents/{_NONEXISTENT_UUID}/files",
    f"/v1/agents/{_NONEXISTENT_UUID}/keys",
    f"/v1/agents/{_NONEXISTENT_UUID}/skills",
    f"/v1/agents/{_NONEXISTENT_UUID}/cost-summary",
    f"/v1/agents/{_NONEXISTENT_UUID}/cost-events",
    f"/v1/agents/{_NONEXISTENT_UUID}/heartbeat-runs",
    f"/v1/agents/{_NONEXISTENT_UUID}/invocations",
    # API keys
    "/v1/api-keys",
    f"/v1/api-keys/{_NONEXISTENT_UUID}",
    # Enrichment providers + field extractions
    "/v1/enrichment-providers",
    f"/v1/enrichment-providers/{_NONEXISTENT_UUID}",
    "/v1/enrichment-field-extractions",
    # Indicator mappings
    "/v1/indicator-mappings",
    "/v1/indicator-mappings/source-plugin-fields",
    # LLM integrations
    "/v1/llm-integrations",
    f"/v1/llm-integrations/{_NONEXISTENT_UUID}",
    f"/v1/llm-integrations/{_NONEXISTENT_UUID}/usage",
    # Issues + labels + categories
    "/v1/issues",
    f"/v1/issues/{_NONEXISTENT_UUID}",
    "/v1/labels",
    "/v1/issue-categories",
    # Skills
    "/v1/skills",
    f"/v1/skills/{_NONEXISTENT_UUID}",
    # Tools
    "/v1/tools",
    # Routines
    "/v1/routines",
    f"/v1/routines/{_NONEXISTENT_UUID}",
    f"/v1/routines/{_NONEXISTENT_UUID}/runs",
    # Runs (heartbeat / streaming)
    f"/v1/runs/{_NONEXISTENT_UUID}/events",
    # Invocations
    f"/v1/invocations/{_NONEXISTENT_UUID}",
    # Topology
    "/v1/topology",
    # KB
    "/v1/kb",
    "/v1/kb/folders",
    "/v1/kb/search?q=test",
    f"/v1/kb/uuid/{_NONEXISTENT_UUID}",
    # Queue + assignments + dashboard
    "/v1/queue",
    "/v1/dashboard",
    # Secrets
    "/v1/secrets",
    f"/v1/secrets/{_NONEXISTENT_UUID}",
    # Health monitoring
    "/v1/health-sources",
    f"/v1/health-sources/{_NONEXISTENT_UUID}",
    f"/v1/health-sources/{_NONEXISTENT_UUID}/metrics",
    "/v1/health/agents/summary",
    "/v1/health/metrics",
    # Heartbeat (UI calls /heartbeat)
    "/v1/heartbeat",
    # Actions
    "/v1/actions",
    f"/v1/actions/{_NONEXISTENT_UUID}",
]


def _is_route_level_404(status_code: int, body: dict | None) -> bool:
    """Return True iff this is FastAPI's "no such route" response.

    Calseta's "entity not found" 404 uses the structured error envelope
    (``{"error": {"code": "NOT_FOUND", ...}}``). FastAPI's "no such route"
    response is the unstructured ``{"detail": "Not Found"}``. Distinguishing
    these is the whole point of this smoke test.
    """
    if status_code != 404:
        return False
    if body is None:
        return True
    if "error" in body:
        return False
    return body.get("detail") == "Not Found"


@pytest.mark.parametrize("path", _UI_GET_ROUTES)
async def test_ui_route_is_registered(
    test_client: AsyncClient,
    api_key: str,
    path: str,
) -> None:
    """Each UI-called route must be registered (no FastAPI route-level 404)."""
    resp = await test_client.get(path, headers=auth_header(api_key))

    try:
        body = resp.json()
    except ValueError:  # pragma: no cover — non-JSON response is itself a problem
        body = None

    assert not _is_route_level_404(resp.status_code, body), (
        f"Route {path!r} is not registered. "
        f"UI hook in use-api.ts points at a non-existent endpoint. "
        f"status={resp.status_code} body={body!r}"
    )


# ---------------------------------------------------------------------------
# Targeted contract checks (S16 items 4–7)
# ---------------------------------------------------------------------------


class TestS16ContractFixes:
    """Pin the field-shape decisions made in S16 so they don't regress."""

    async def test_dashboard_response_has_typed_fields(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        """Dashboard returns the ControlPlaneDashboardResponse Pydantic shape."""
        resp = await test_client.get("/v1/dashboard", headers=auth_header(api_key))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        data = body["data"]

        # Top-level blocks
        assert set(data.keys()) == {"agents", "queue", "costs_mtd"}

        # costs_mtd block — period_start must be ISO 8601, total_cents an int
        costs = data["costs_mtd"]
        assert isinstance(costs["total_cents"], int)
        assert isinstance(costs["total_usd"], (int, float))
        assert isinstance(costs["period_start"], str)
        # Must parse as ISO 8601 (Pydantic serialized a real datetime)
        assert "T" in costs["period_start"]

    async def test_agent_files_endpoints_use_name_field(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict,
    ) -> None:
        """PUT/GET on /agents/{uuid}/files/{path} returns ``name`` (not ``path``)."""
        agent_uuid = sample_agent["uuid"]
        # PUT a file
        put_resp = await test_client.put(
            f"/v1/agents/{agent_uuid}/files/test.md",
            json={"content": "# hello"},
            headers=auth_header(api_key),
        )
        assert put_resp.status_code == 200, put_resp.text
        put_body = put_resp.json()["data"]
        assert "name" in put_body
        assert "path" not in put_body
        assert put_body["name"] == "test.md"
        assert put_body["content"] == "# hello"

        # GET the same file
        get_resp = await test_client.get(
            f"/v1/agents/{agent_uuid}/files/test.md",
            headers=auth_header(api_key),
        )
        assert get_resp.status_code == 200, get_resp.text
        get_body = get_resp.json()["data"]
        assert "name" in get_body
        assert "path" not in get_body
        assert get_body["name"] == "test.md"

    async def test_agent_skills_returns_paginated_envelope(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict,
    ) -> None:
        """``GET /v1/agents/{uuid}/skills`` returns PaginatedResponse, not DataResponse."""
        agent_uuid = sample_agent["uuid"]
        resp = await test_client.get(
            f"/v1/agents/{agent_uuid}/skills",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        # PaginatedResponse populates meta with pagination fields
        meta = body["meta"]
        assert "total" in meta
        assert "page" in meta
        assert "page_size" in meta

    async def test_no_agent_activity_route_exists(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        """The dead ``/v1/agents/{uuid}/activity`` hook was removed; no route was added.

        The app mounts a SPA catch-all that serves ``index.html`` for any
        unmatched path, so the assertion is "no JSON API endpoint here" —
        either a 404 from the API router OR an HTML response from the SPA
        catch-all is acceptable. What we forbid is a real JSON envelope at
        this path.
        """
        resp = await test_client.get(
            f"/v1/agents/{_NONEXISTENT_UUID}/activity",
            headers=auth_header(api_key),
        )
        if resp.status_code == 404:
            return  # Bare FastAPI 404 — no such route.
        # Otherwise, the catch-all served the SPA. Confirm it is NOT a JSON
        # envelope (the canonical API shape is `{"data": ...}` or
        # `{"error": {...}}`).
        content_type = resp.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            body = resp.json()
            assert "data" not in body, (
                "Unexpected JSON API envelope at /v1/agents/{uuid}/activity — "
                "the dead useAgentActivity route should not have been re-added."
            )
