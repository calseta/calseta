"""Integration tests for S13 — capabilities.tools → tool_ids resolution.

Covers the AgentService write path (POST/PATCH /v1/agents) and the
``scripts/backfill_tool_ids.py`` one-shot.

Test surface (per S13 acceptance criteria):
    1. POST with capabilities.tools=["nonexistent_tool"] → 422 with the bad
       slug surfaced in the error body.
    2. POST with valid slugs → tool_ids is populated to match.
    3. PATCH that adds capabilities.tools → tool_ids is rewritten; unknown
       slugs still rejected on PATCH.
    4. Backfill script — pre-seed an agent with empty tool_ids + valid
       capabilities.tools; run script; assert tool_ids populated.
       Re-run; assert no diff (idempotent).
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.agent_tool import AgentTool
from scripts.backfill_tool_ids import backfill
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Local fixtures — seed a small set of agent_tools rows for these tests.
# The app-startup builtin seeder (`seed_builtin_tools`) does not run during
# pytest because httpx ASGITransport skips the lifespan handler.
# ---------------------------------------------------------------------------


def _make_tool(slug: str, category: str = "investigation", tier: str = "safe") -> AgentTool:
    """Build a minimal AgentTool row suitable for resolver/backfill tests."""
    return AgentTool(
        id=slug,
        display_name=slug.replace("_", " ").title(),
        description=f"Test tool: {slug}",
        documentation=None,
        tier=tier,
        category=category,
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        handler_ref=f"app.integrations.tools.handlers.{slug}",
        is_active=True,
    )


@pytest_asyncio.fixture
async def seeded_tools(db_session: AsyncSession) -> list[str]:
    """Insert a deterministic set of agent_tools rows for resolution tests."""
    slugs = ["get_alert", "search_alerts", "post_finding", "update_alert_status"]
    for slug in slugs:
        existing = await db_session.get(AgentTool, slug)
        if existing is None:
            db_session.add(_make_tool(slug))
    await db_session.flush()
    return slugs


# ---------------------------------------------------------------------------
# 1. AgentService.create — slug resolution + 422 on unknown slugs
# ---------------------------------------------------------------------------


class TestCreateAgentToolResolution:
    async def test_create_resolves_capability_slugs_into_tool_ids(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-create-{uuid.uuid4().hex[:8]}",
                "description": "tool-id resolver smoke test",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {
                    "tools": ["get_alert", "post_finding"],
                    "role": "investigator",
                },
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        # Order should be preserved from capabilities.tools
        assert data["tool_ids"] == ["get_alert", "post_finding"]
        # capabilities itself is unchanged
        assert data["capabilities"]["tools"] == ["get_alert", "post_finding"]

    async def test_create_with_unknown_slug_returns_422(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-bad-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {"tools": ["get_alert", "totally_made_up_tool"]},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["error"]["code"] == "UNKNOWN_TOOL_SLUG"
        # The offending slug must appear in the error body — operators
        # need to see exactly what they got wrong.
        assert "totally_made_up_tool" in body["error"]["message"]
        assert body["error"]["details"]["unknown_slugs"] == [
            "totally_made_up_tool"
        ]

    async def test_create_with_mixed_unknown_slugs_lists_them_all(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-mixed-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {
                    "tools": [
                        "get_alert",
                        "delegate_task",  # unknown
                        "post_finding",
                        "enrich_indicator",  # unknown
                    ]
                },
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422, resp.text
        unknown = resp.json()["error"]["details"]["unknown_slugs"]
        assert sorted(unknown) == ["delegate_task", "enrich_indicator"]

    async def test_create_without_capabilities_does_not_touch_tool_ids(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        # When the caller omits capabilities entirely, the resolver is a
        # no-op — tool_ids passed explicitly is honoured.
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-explicit-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "tool_ids": ["get_alert"],
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["tool_ids"] == ["get_alert"]

    async def test_create_with_empty_capability_tools_writes_empty_list(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-empty-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {"tools": []},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201, resp.text
        # Operator declared "no tools" — that intent must be persisted.
        assert resp.json()["data"]["tool_ids"] == []

    async def test_create_with_non_list_tools_returns_422(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-bad-shape-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {"tools": "get_alert"},  # str, not list
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "INVALID_CAPABILITIES"


# ---------------------------------------------------------------------------
# 2. AgentService.patch — slug resolution + 422 on unknown slugs
# ---------------------------------------------------------------------------


class TestPatchAgentToolResolution:
    async def test_patch_capabilities_rewrites_tool_ids(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        # Create with one tool
        create_resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-patch-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "capabilities": {"tools": ["get_alert"]},
            },
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201, create_resp.text
        agent_uuid = create_resp.json()["data"]["uuid"]
        assert create_resp.json()["data"]["tool_ids"] == ["get_alert"]

        # Patch with a broader tool set
        patch_resp = await test_client.patch(
            f"/v1/agents/{agent_uuid}",
            json={
                "capabilities": {
                    "tools": ["get_alert", "search_alerts", "post_finding"],
                    "role": "investigator",
                }
            },
            headers=auth_header(api_key),
        )
        assert patch_resp.status_code == 200, patch_resp.text
        data = patch_resp.json()["data"]
        assert data["tool_ids"] == ["get_alert", "search_alerts", "post_finding"]

    async def test_patch_unknown_slug_returns_422(
        self,
        test_client: AsyncClient,
        api_key: str,
        seeded_tools: list[str],
    ) -> None:
        create_resp = await test_client.post(
            "/v1/agents",
            json={
                "name": f"resolver-test-patch-bad-{uuid.uuid4().hex[:8]}",
                "endpoint_url": "http://localhost:9999/hook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
            },
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201, create_resp.text
        agent_uuid = create_resp.json()["data"]["uuid"]

        patch_resp = await test_client.patch(
            f"/v1/agents/{agent_uuid}",
            json={"capabilities": {"tools": ["never_seen_before"]}},
            headers=auth_header(api_key),
        )
        assert patch_resp.status_code == 422, patch_resp.text
        body = patch_resp.json()
        assert body["error"]["code"] == "UNKNOWN_TOOL_SLUG"
        assert "never_seen_before" in body["error"]["message"]


# ---------------------------------------------------------------------------
# 3. Backfill script — idempotency and write-correctness
# ---------------------------------------------------------------------------


class TestBackfillScript:
    async def test_backfill_populates_empty_tool_ids(
        self,
        db_session: AsyncSession,
        seeded_tools: list[str],
    ) -> None:
        # Pre-seed: agent with capabilities.tools but tool_ids=[]
        agent = AgentRegistration(
            uuid=uuid.uuid4(),
            name=f"backfill-target-{uuid.uuid4().hex[:8]}",
            description="Pre-resolver agent",
            endpoint_url="http://localhost:9999/hook",
            auth_header_name=None,
            auth_header_value_encrypted=None,
            trigger_on_sources=[],
            trigger_on_severities=[],
            trigger_filter=None,
            timeout_seconds=30,
            retry_count=3,
            documentation=None,
            status="active",
            execution_mode="external",
            agent_type="standalone",
            role=None,
            capabilities={"tools": ["get_alert", "post_finding"]},
            adapter_type="webhook",
            adapter_config=None,
            llm_integration_id=None,
            system_prompt=None,
            methodology=None,
            tool_ids=[],  # the bug we are fixing
            max_tokens=None,
            enable_thinking=False,
            instruction_files=None,
            sub_agent_ids=None,
            max_sub_agent_calls=None,
            budget_monthly_cents=0,
            max_concurrent_alerts=1,
            max_cost_per_alert_cents=0,
            max_investigation_minutes=0,
            stall_threshold=0,
            memory_promotion_requires_approval=False,
        )
        db_session.add(agent)
        await db_session.flush()

        stats = await backfill(db_session, dry_run=False)

        assert stats["agents_updated"] >= 1
        await db_session.refresh(agent)
        assert agent.tool_ids == ["get_alert", "post_finding"]

    async def test_backfill_is_idempotent(
        self,
        db_session: AsyncSession,
        seeded_tools: list[str],
    ) -> None:
        # Pre-seed an already-correct agent
        agent = AgentRegistration(
            uuid=uuid.uuid4(),
            name=f"backfill-idempotent-{uuid.uuid4().hex[:8]}",
            description="Already resolved",
            endpoint_url="http://localhost:9999/hook",
            auth_header_name=None,
            auth_header_value_encrypted=None,
            trigger_on_sources=[],
            trigger_on_severities=[],
            trigger_filter=None,
            timeout_seconds=30,
            retry_count=3,
            documentation=None,
            status="active",
            execution_mode="external",
            agent_type="standalone",
            role=None,
            capabilities={"tools": ["search_alerts"]},
            adapter_type="webhook",
            adapter_config=None,
            llm_integration_id=None,
            system_prompt=None,
            methodology=None,
            tool_ids=["search_alerts"],
            max_tokens=None,
            enable_thinking=False,
            instruction_files=None,
            sub_agent_ids=None,
            max_sub_agent_calls=None,
            budget_monthly_cents=0,
            max_concurrent_alerts=1,
            max_cost_per_alert_cents=0,
            max_investigation_minutes=0,
            stall_threshold=0,
            memory_promotion_requires_approval=False,
        )
        db_session.add(agent)
        await db_session.flush()

        first = await backfill(db_session, dry_run=False)
        # On the second pass, no agents should be updated.
        second = await backfill(db_session, dry_run=False)

        assert second["agents_updated"] == 0
        # The agent we created appears in already-correct on at least one pass
        assert (
            first["agents_already_correct"] + second["agents_already_correct"]
        ) >= 1
        await db_session.refresh(agent)
        assert agent.tool_ids == ["search_alerts"]

    async def test_backfill_skips_unknown_slugs_with_warning(
        self,
        db_session: AsyncSession,
        seeded_tools: list[str],
    ) -> None:
        # Mix of known and aspirational slugs — backfill should keep
        # only the known ones, surface the unknowns in stats.
        agent = AgentRegistration(
            uuid=uuid.uuid4(),
            name=f"backfill-mixed-{uuid.uuid4().hex[:8]}",
            description="Has aspirational tools",
            endpoint_url="http://localhost:9999/hook",
            auth_header_name=None,
            auth_header_value_encrypted=None,
            trigger_on_sources=[],
            trigger_on_severities=[],
            trigger_filter=None,
            timeout_seconds=30,
            retry_count=3,
            documentation=None,
            status="active",
            execution_mode="external",
            agent_type="standalone",
            role=None,
            capabilities={
                "tools": ["get_alert", "delegate_task", "post_finding"]
            },
            adapter_type="webhook",
            adapter_config=None,
            llm_integration_id=None,
            system_prompt=None,
            methodology=None,
            tool_ids=[],
            max_tokens=None,
            enable_thinking=False,
            instruction_files=None,
            sub_agent_ids=None,
            max_sub_agent_calls=None,
            budget_monthly_cents=0,
            max_concurrent_alerts=1,
            max_cost_per_alert_cents=0,
            max_investigation_minutes=0,
            stall_threshold=0,
            memory_promotion_requires_approval=False,
        )
        db_session.add(agent)
        await db_session.flush()

        stats = await backfill(db_session, dry_run=False)

        assert "delegate_task" in stats["unknown_slugs"]
        await db_session.refresh(agent)
        assert agent.tool_ids == ["get_alert", "post_finding"]
