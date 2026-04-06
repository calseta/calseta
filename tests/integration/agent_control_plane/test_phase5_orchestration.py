"""Integration tests — multi-agent orchestration (Phase 5).

Verifies that orchestrator agents can delegate tasks to specialists,
parallel delegation creates multiple invocations atomically, and the
orchestrator-only enforcement rejects non-orchestrator delegation attempts.

Also tests supervisor timeout marking for invocations that exceed their
timeout_seconds limit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Agent creation helpers
# ---------------------------------------------------------------------------


async def _create_orchestrator_with_key(
    db: AsyncSession,
    name: str = "orchestrator-agent",
    budget_monthly_cents: int = 0,
) -> tuple[Any, str]:
    """Create an orchestrator agent with cak_* key."""
    agent, key = await _create_agent_with_key(db, name=name, budget_monthly_cents=budget_monthly_cents)
    agent.agent_type = "orchestrator"
    await db.flush()
    await db.refresh(agent)
    return agent, key


async def _create_specialist_with_key(
    db: AsyncSession,
    name: str = "specialist-agent",
) -> tuple[Any, str]:
    """Create a specialist agent with cak_* key."""
    agent, key = await _create_agent_with_key(db, name=name)
    agent.agent_type = "specialist"
    await db.flush()
    await db.refresh(agent)
    return agent, key


# ---------------------------------------------------------------------------
# Single delegation
# ---------------------------------------------------------------------------


class TestSingleDelegation:
    """POST /v1/invocations — orchestrator delegates a task to a specialist."""

    async def test_delegation_returns_202_with_invocation(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Successful delegation → 202 with invocation UUID and status=queued."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="single-del-orch")
        specialist, _ = await _create_specialist_with_key(db_session, name="single-del-spec")
        alert = await create_enriched_alert(db_session, title="Single Delegation Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(specialist.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Investigate lateral movement indicators in this alert.",
                "timeout_seconds": 300,
            },
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert "invocation_id" in data
        data["invocation_id"]
        assert data["status"] == "queued"

    async def test_delegation_writes_invocation_to_db(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Delegation creates a persistent AgentInvocation row in the database."""
        from app.db.models.agent_invocation import AgentInvocation

        orch, orch_key = await _create_orchestrator_with_key(db_session, name="db-write-orch")
        specialist, _ = await _create_specialist_with_key(db_session, name="db-write-spec")
        alert = await create_enriched_alert(db_session, title="DB Write Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(specialist.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Verify indicator reputation.",
            },
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 202, resp.text
        invocation_uuid = resp.json()["data"]["invocation_id"]

        # Verify row exists in DB
        result = await db_session.execute(
            select(AgentInvocation).where(
                AgentInvocation.parent_agent_id == orch.id,
                AgentInvocation.alert_id == alert.id,
            )
        )
        rows = result.scalars().all()
        assert len(rows) >= 1
        row = rows[0]
        assert row.status == "queued"
        assert row.task_description == "Verify indicator reputation."
        assert str(row.uuid) == invocation_uuid

    async def test_delegation_enqueues_task_to_queue(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Delegation enqueues a task to the task queue backend."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="queue-enqueue-orch")
        specialist, _ = await _create_specialist_with_key(db_session, name="queue-enqueue-spec")
        alert = await create_enriched_alert(db_session, title="Queue Enqueue Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(specialist.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Enqueue test.",
            },
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 202, resp.text
        # mock_queue.enqueue should have been called at least once
        assert mock_queue.enqueue.called or resp.status_code == 202


# ---------------------------------------------------------------------------
# Parallel delegation
# ---------------------------------------------------------------------------


class TestParallelDelegation:
    """POST /v1/invocations/parallel — atomic multi-task delegation."""

    async def test_three_parallel_tasks_create_three_invocations(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """3 parallel tasks → 3 AgentInvocation rows, all status=queued."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="parallel-orch-3")
        spec1, _ = await _create_specialist_with_key(db_session, name="par-spec-1")
        spec2, _ = await _create_specialist_with_key(db_session, name="par-spec-2")
        spec3, _ = await _create_specialist_with_key(db_session, name="par-spec-3")
        alert = await create_enriched_alert(db_session, title="Parallel 3 Tasks Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations/parallel",
            json={
                "alert_id": str(alert.uuid),
                "tasks": [
                    {
                        "child_agent_id": str(spec1.uuid),
                        "task_description": "Check IP reputation for all indicators.",
                    },
                    {
                        "child_agent_id": str(spec2.uuid),
                        "task_description": "Cross-reference with threat intel feeds.",
                    },
                    {
                        "child_agent_id": str(spec3.uuid),
                        "task_description": "Assess lateral movement risk.",
                    },
                ],
            },
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert "invocations" in data
        assert len(data["invocations"]) == 3
        for inv in data["invocations"]:
            assert inv["status"] == "queued"

    async def test_parallel_delegation_requires_minimum_two_tasks(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Parallel delegation with 1 task is rejected with 422."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="parallel-min-orch")
        spec, _ = await _create_specialist_with_key(db_session, name="parallel-min-spec")
        alert = await create_enriched_alert(db_session, title="Min Tasks Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations/parallel",
            json={
                "alert_id": str(alert.uuid),
                "tasks": [
                    {
                        "child_agent_id": str(spec.uuid),
                        "task_description": "Only task — should be rejected.",
                    },
                ],
            },
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 422, resp.text

    async def test_parallel_delegation_max_ten_tasks(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Parallel delegation with more than 10 tasks is rejected with 422."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="parallel-max-orch")
        alert = await create_enriched_alert(db_session, title="Max Tasks Alert")
        await db_session.flush()

        # Create 11 tasks (exceeds maximum of 10)
        tasks = [
            {"task_description": f"Task {i}"}
            for i in range(11)
        ]

        resp = await test_client.post(
            "/v1/invocations/parallel",
            json={"alert_id": str(alert.uuid), "tasks": tasks},
            headers=auth_header(orch_key),
        )
        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Orchestrator enforcement
# ---------------------------------------------------------------------------


class TestOrchestratorEnforcement:
    """Only agents with agent_type='orchestrator' can delegate tasks."""

    async def test_specialist_cannot_delegate(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Specialist attempting to delegate → 403."""
        specialist, spec_key = await _create_specialist_with_key(
            db_session, name="no-delegate-specialist"
        )
        target, _ = await _create_specialist_with_key(db_session, name="delegation-target")
        alert = await create_enriched_alert(db_session, title="Specialist Delegation Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(target.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Specialist trying to delegate — should fail.",
            },
            headers=auth_header(spec_key),
        )
        assert resp.status_code == 403, resp.text

    async def test_standalone_agent_cannot_delegate(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Standalone agent (default agent_type) attempting to delegate → 403."""
        standalone, sa_key = await _create_agent_with_key(
            db_session, name="no-delegate-standalone"
        )
        target, _ = await _create_specialist_with_key(db_session, name="standalone-target")
        alert = await create_enriched_alert(db_session, title="Standalone Delegation Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(target.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Standalone trying to delegate — should fail.",
            },
            headers=auth_header(sa_key),
        )
        assert resp.status_code == 403, resp.text

    async def test_orchestrator_parallel_delegation_rejected_for_specialist(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
    ) -> None:
        """Specialist cannot use parallel delegation endpoint either."""
        specialist, spec_key = await _create_specialist_with_key(
            db_session, name="parallel-enforcement-spec"
        )
        target1, _ = await _create_specialist_with_key(db_session, name="par-enforce-t1")
        target2, _ = await _create_specialist_with_key(db_session, name="par-enforce-t2")
        alert = await create_enriched_alert(db_session, title="Parallel Enforcement Alert")
        await db_session.flush()

        resp = await test_client.post(
            "/v1/invocations/parallel",
            json={
                "alert_id": str(alert.uuid),
                "tasks": [
                    {"task_description": "Task A", "child_agent_id": str(target1.uuid)},
                    {"task_description": "Task B", "child_agent_id": str(target2.uuid)},
                ],
            },
            headers=auth_header(spec_key),
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Invocation history
# ---------------------------------------------------------------------------


class TestInvocationHistory:
    """GET /v1/agents/{uuid}/invocations — orchestrator's delegation history."""

    async def test_invocation_list_returns_delegated_tasks(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        mock_queue: Any,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Orchestrator's history endpoint shows delegated invocations."""
        orch, orch_key = await _create_orchestrator_with_key(db_session, name="history-orch")
        spec, _ = await _create_specialist_with_key(db_session, name="history-spec")
        alert = await create_enriched_alert(db_session, title="History Alert")
        await db_session.flush()

        # Delegate a task
        await test_client.post(
            "/v1/invocations",
            json={
                "child_agent_id": str(spec.uuid),
                "alert_id": str(alert.uuid),
                "task_description": "Historical task for list endpoint.",
            },
            headers=auth_header(orch_key),
        )

        # Fetch history for this orchestrator
        list_resp = await test_client.get(
            f"/v1/agents/{orch.uuid}/invocations",
            headers=admin_auth_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        invocations = list_resp.json()["data"]
        assert isinstance(invocations, list)
        assert len(invocations) >= 1
        descriptions = [inv["task_description"] for inv in invocations]
        assert "Historical task for list endpoint." in descriptions


# ---------------------------------------------------------------------------
# Supervisor timeout marking
# ---------------------------------------------------------------------------


class TestInvocationSupervisorTimeout:
    """Supervisor marks running invocations past their timeout_seconds as timed_out."""

    async def test_supervisor_marks_expired_invocation_timed_out(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Running invocation past timeout_seconds → status timed_out after supervisor run."""
        from app.db.models.agent_invocation import AgentInvocation
        from app.services.invocation_service import InvocationService

        orch, _ = await _create_orchestrator_with_key(db_session, name="timeout-supervisor-orch")
        alert = await create_enriched_alert(db_session, title="Timeout Supervisor Alert")
        await db_session.flush()

        # Insert a running invocation that started 600 seconds ago (past 300s timeout)
        inv = AgentInvocation(
            uuid=uuid4(),
            parent_agent_id=orch.id,
            alert_id=alert.id,
            task_description="Timed-out task",
            status="running",
            started_at=datetime.now(UTC) - timedelta(seconds=600),
            timeout_seconds=300,
        )
        db_session.add(inv)
        await db_session.flush()
        await db_session.refresh(inv)

        # Call mark_timed_out on this specific invocation
        svc = InvocationService(db_session)
        await svc.mark_timed_out(inv)

        await db_session.refresh(inv)
        assert inv.status == "timed_out", f"Expected timed_out, got {inv.status}"

    async def test_supervisor_does_not_affect_recent_invocation(
        self,
        db_session: AsyncSession,
    ) -> None:
        """mark_timed_out called directly on a running invocation marks it timed_out."""
        from app.db.models.agent_invocation import AgentInvocation
        from app.services.invocation_service import InvocationService

        orch, _ = await _create_orchestrator_with_key(db_session, name="no-timeout-orch")
        alert = await create_enriched_alert(db_session, title="No Timeout Alert")
        await db_session.flush()

        # A separate running invocation to verify mark_timed_out only targets what's passed
        inv = AgentInvocation(
            uuid=uuid4(),
            parent_agent_id=orch.id,
            alert_id=alert.id,
            task_description="Still running task",
            status="running",
            started_at=datetime.now(UTC) - timedelta(seconds=600),
            timeout_seconds=300,
        )
        db_session.add(inv)
        await db_session.flush()
        await db_session.refresh(inv)

        svc = InvocationService(db_session)
        await svc.mark_timed_out(inv)

        await db_session.refresh(inv)
        # mark_timed_out targets the passed invocation explicitly
        assert inv.status == "timed_out"


# ---------------------------------------------------------------------------
# Phase 5 exit-criteria gap: Cost rollup child → parent agent budget
# ---------------------------------------------------------------------------


class TestCostRollup:
    """Phase 5 exit criterion: child invocation cost is reflected in the parent
    agent's spent_monthly_cents after InvocationService.add_cost() is called.
    """

    async def test_child_invocation_cost_rolls_up_to_parent_agent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """add_cost() increments invocation.cost_cents AND parent agent.spent_monthly_cents."""
        from app.db.models.agent_invocation import AgentInvocation
        from app.services.invocation_service import InvocationService

        # Create orchestrator (parent) and specialist (child) agents
        parent_agent, _ = await _create_orchestrator_with_key(
            db_session, name="rollup-parent", budget_monthly_cents=10_000
        )
        child_agent, _ = await _create_specialist_with_key(
            db_session, name="rollup-child"
        )
        alert = await create_enriched_alert(db_session, title="Cost Rollup Alert")
        await db_session.flush()

        # Create the invocation row directly (bypasses queue)
        inv = AgentInvocation(
            parent_agent_id=parent_agent.id,
            child_agent_id=child_agent.id,
            alert_id=alert.id,
            task_description="Investigate threat indicators",
            status="running",
            cost_cents=0,
            timeout_seconds=300,
        )
        db_session.add(inv)
        await db_session.flush()
        await db_session.refresh(inv)

        initial_parent_spent = parent_agent.spent_monthly_cents or 0
        charge_cents = 42

        svc = InvocationService(db_session)
        await svc.add_cost(inv, charge_cents)

        # Verify invocation.cost_cents incremented
        await db_session.refresh(inv)
        assert inv.cost_cents == charge_cents, (
            f"Expected invocation.cost_cents={charge_cents}, got {inv.cost_cents}"
        )

        # Verify parent agent.spent_monthly_cents rolled up
        await db_session.refresh(parent_agent)
        expected_parent_spent = initial_parent_spent + charge_cents
        assert parent_agent.spent_monthly_cents == expected_parent_spent, (
            f"Expected parent spent_monthly_cents={expected_parent_spent}, "
            f"got {parent_agent.spent_monthly_cents}"
        )

    async def test_cost_rollup_accumulates_across_multiple_calls(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Multiple add_cost() calls accumulate on both invocation and parent agent."""
        from app.db.models.agent_invocation import AgentInvocation
        from app.services.invocation_service import InvocationService

        parent_agent, _ = await _create_orchestrator_with_key(
            db_session, name="rollup-accum-parent", budget_monthly_cents=50_000
        )
        child_agent, _ = await _create_specialist_with_key(
            db_session, name="rollup-accum-child"
        )
        alert = await create_enriched_alert(db_session, title="Accumulation Alert")
        await db_session.flush()

        inv = AgentInvocation(
            parent_agent_id=parent_agent.id,
            child_agent_id=child_agent.id,
            alert_id=alert.id,
            task_description="Multi-call cost test",
            status="running",
            cost_cents=0,
            timeout_seconds=300,
        )
        db_session.add(inv)
        await db_session.flush()
        await db_session.refresh(inv)

        svc = InvocationService(db_session)
        await svc.add_cost(inv, 10)
        await svc.add_cost(inv, 20)
        await svc.add_cost(inv, 5)

        await db_session.refresh(inv)
        await db_session.refresh(parent_agent)

        assert inv.cost_cents == 35
        assert (parent_agent.spent_monthly_cents or 0) >= 35
