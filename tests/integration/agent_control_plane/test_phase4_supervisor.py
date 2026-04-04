"""
Integration tests for Phase 4 — AgentSupervisor, budget enforcement, and cost reporting.

Covers:
  AgentSupervisor.supervise()        Timeout detection → release assignment + activity event
  AgentSupervisor._check_budget()    Budget hard stop → pause agent + release + activity events
  CostService.record_cost()          Soft-warn at 80% → cost.budget_alert activity event
  CostService.record_cost()          Hard stop at 100% → agent paused + cost.hard_stop event
  PATCH /v1/agents/{uuid}/budget     Operator updates budget
  POST  /v1/agents/{uuid}/pause      Operator pause
  POST  /v1/agents/{uuid}/resume     Operator resume
  GET   /v1/costs/summary            Instance-wide cost aggregate
  GET   /v1/costs/by-agent           Per-agent cost breakdown
  GET   /v1/costs/by-alert           Per-alert cost breakdown
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activity_event import ActivityEvent
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert_assignment import AlertAssignment
from app.runtime.supervisor import AgentSupervisor
from app.schemas.cost_events import CostEventCreate
from app.services.cost_service import CostService
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _checkout_alert(
    db: AsyncSession,
    agent: AgentRegistration,
) -> AlertAssignment:
    """Directly create an in_progress AlertAssignment in the DB (bypasses queue service)."""
    alert = await create_enriched_alert(db)
    assignment = AlertAssignment(
        alert_id=alert.id,
        agent_registration_id=agent.id,
        status="in_progress",
        checked_out_at=datetime.now(UTC),
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


async def _get_activity_events(
    db: AsyncSession,
    event_type: str,
) -> list[ActivityEvent]:
    result = await db.execute(
        select(ActivityEvent).where(ActivityEvent.event_type == event_type)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Supervisor — timeout detection
# ---------------------------------------------------------------------------


class TestSupervisorTimeout:
    async def test_timeout_releases_assignment(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Supervisor detects stuck assignment and releases it when elapsed > timeout."""
        agent, _ = await _create_agent_with_key(
            db_session, name="timeout-agent", status="active"
        )
        # Set timeout to 1 second so we can trigger it immediately
        agent.timeout_seconds = 1
        agent.execution_mode = "managed"
        await db_session.flush()

        # Create assignment with checkout_at in the past
        assignment = await _checkout_alert(db_session, agent)
        assignment.checked_out_at = datetime.now(UTC) - timedelta(seconds=10)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        report = await supervisor.supervise()

        assert report.timed_out == 1
        assert report.checked >= 1

        # Assignment should be released
        await db_session.refresh(assignment)
        assert assignment.status == "released"

    async def test_timeout_emits_activity_event(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Supervisor logs heartbeat.timed_out activity event on timeout."""
        agent, _ = await _create_agent_with_key(
            db_session, name="timeout-event-agent", status="active"
        )
        agent.timeout_seconds = 1
        agent.execution_mode = "managed"
        await db_session.flush()

        assignment = await _checkout_alert(db_session, agent)
        assignment.checked_out_at = datetime.now(UTC) - timedelta(seconds=10)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        await supervisor.supervise()

        events = await _get_activity_events(db_session, "heartbeat.timed_out")
        assert len(events) >= 1
        matching = [e for e in events if e.references and e.references.get("agent_id") == agent.id]
        assert len(matching) == 1

    async def test_no_timeout_for_recent_heartbeat(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Agent with recent heartbeat is not timed out."""
        agent, _ = await _create_agent_with_key(
            db_session, name="fresh-agent", status="active"
        )
        agent.timeout_seconds = 300
        agent.execution_mode = "managed"
        agent.last_heartbeat_at = datetime.now(UTC)  # just now
        await db_session.flush()

        assignment = await _checkout_alert(db_session, agent)
        assignment.checked_out_at = datetime.now(UTC) - timedelta(seconds=10)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        report = await supervisor.supervise()

        assert report.timed_out == 0
        await db_session.refresh(assignment)
        assert assignment.status == "in_progress"

    async def test_external_agents_not_supervised(
        self,
        db_session: AsyncSession,
    ) -> None:
        """External agents are skipped by the supervisor."""
        agent, _ = await _create_agent_with_key(
            db_session, name="external-agent", status="active"
        )
        agent.timeout_seconds = 1
        agent.execution_mode = "external"
        await db_session.flush()

        assignment = await _checkout_alert(db_session, agent)
        assignment.checked_out_at = datetime.now(UTC) - timedelta(seconds=120)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        report = await supervisor.supervise()

        assert report.timed_out == 0
        await db_session.refresh(assignment)
        assert assignment.status == "in_progress"


# ---------------------------------------------------------------------------
# Supervisor — budget enforcement
# ---------------------------------------------------------------------------


class TestSupervisorBudget:
    async def test_over_budget_assignment_released(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Supervisor detects over-budget agent with active assignment → pauses + releases."""
        agent, _ = await _create_agent_with_key(
            db_session, name="overbudget-agent", status="active"
        )
        agent.execution_mode = "managed"
        agent.budget_monthly_cents = 1000
        agent.spent_monthly_cents = 1500  # already over budget
        agent.timeout_seconds = 99999  # no timeout
        await db_session.flush()

        assignment = await _checkout_alert(db_session, agent)
        assignment.checked_out_at = datetime.now(UTC)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        report = await supervisor.supervise()

        assert report.budget_stopped == 1

        await db_session.refresh(agent)
        assert agent.status == "paused"

        await db_session.refresh(assignment)
        assert assignment.status == "released"

    async def test_over_budget_emits_activity_events(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Supervisor emits cost.hard_stop and agent.budget_exceeded events on budget stop."""
        agent, _ = await _create_agent_with_key(
            db_session, name="budget-event-agent", status="active"
        )
        agent.execution_mode = "managed"
        agent.budget_monthly_cents = 500
        agent.spent_monthly_cents = 600
        agent.timeout_seconds = 99999
        await db_session.flush()

        await _checkout_alert(db_session, agent)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        await supervisor.supervise()

        hard_stop_events = await _get_activity_events(db_session, "cost.hard_stop")
        budget_exceeded_events = await _get_activity_events(db_session, "agent.budget_exceeded")

        assert any(
            e.references and e.references.get("agent_id") == agent.id
            for e in hard_stop_events
        ), "cost.hard_stop event not found"
        assert any(
            e.references and e.references.get("agent_id") == agent.id
            for e in budget_exceeded_events
        ), "agent.budget_exceeded event not found"

    async def test_no_budget_enforcement_when_no_limit(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Agent with budget_monthly_cents=0 (unlimited) is not stopped by supervisor."""
        agent, _ = await _create_agent_with_key(
            db_session, name="unlimited-agent", status="active"
        )
        agent.execution_mode = "managed"
        agent.budget_monthly_cents = 0
        agent.spent_monthly_cents = 99999
        agent.timeout_seconds = 99999
        await db_session.flush()

        await _checkout_alert(db_session, agent)
        await db_session.flush()

        supervisor = AgentSupervisor(db_session)
        report = await supervisor.supervise()

        assert report.budget_stopped == 0
        await db_session.refresh(agent)
        assert agent.status == "active"


# ---------------------------------------------------------------------------
# CostService — soft warning + hard stop
# ---------------------------------------------------------------------------


class TestCostServiceBudget:
    async def test_soft_warn_activity_event_at_80_pct(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Recording a cost that crosses 80% of budget emits cost.budget_alert activity event."""
        agent, _ = await _create_agent_with_key(
            db_session, name="soft-warn-agent", budget_monthly_cents=1000
        )
        agent.spent_monthly_cents = 790  # just under 80% (800 threshold)
        await db_session.flush()

        svc = CostService(db_session)
        data = CostEventCreate(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cost_cents=20,  # pushes to 810 — crosses 800 threshold
        )
        _, budget_status = await svc.record_cost(agent=agent, data=data)

        assert budget_status.hard_stop_triggered is False  # not yet at 100%

        events = await _get_activity_events(db_session, "cost.budget_alert")
        matching = [
            e for e in events
            if e.references and e.references.get("agent_id") == agent.id
        ]
        assert len(matching) == 1, f"Expected 1 cost.budget_alert event, got {len(matching)}"
        assert (matching[0].references or {})["threshold_pct"] == 80

    async def test_soft_warn_not_emitted_again_if_already_past(
        self,
        db_session: AsyncSession,
    ) -> None:
        """If already past 80%, recording another cost does NOT emit a second soft-warn event."""
        agent, _ = await _create_agent_with_key(
            db_session, name="past-warn-agent", budget_monthly_cents=1000
        )
        agent.spent_monthly_cents = 900  # already past 80%
        await db_session.flush()

        svc = CostService(db_session)
        data = CostEventCreate(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=50,
            output_tokens=20,
            cost_cents=10,
        )
        await svc.record_cost(agent=agent, data=data)

        events = await _get_activity_events(db_session, "cost.budget_alert")
        matching = [
            e for e in events
            if e.references and e.references.get("agent_id") == agent.id
        ]
        # Should be zero — the threshold was already crossed before this recording
        assert len(matching) == 0

    async def test_hard_stop_pauses_agent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Recording a cost that exhausts budget sets agent.status='paused'."""
        agent, _ = await _create_agent_with_key(
            db_session, name="hard-stop-agent", budget_monthly_cents=500
        )
        agent.spent_monthly_cents = 490
        await db_session.flush()

        svc = CostService(db_session)
        data = CostEventCreate(
            provider="openai",
            model="gpt-4o",
            input_tokens=500,
            output_tokens=200,
            cost_cents=20,  # 490 + 20 = 510 >= 500 → hard stop
        )
        _, budget_status = await svc.record_cost(agent=agent, data=data)

        assert budget_status.hard_stop_triggered is True
        assert budget_status.remaining_cents == 0

        await db_session.refresh(agent)
        assert agent.status == "paused"

    async def test_hard_stop_emits_activity_events(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Hard stop emits cost.hard_stop and agent.budget_exceeded activity events."""
        agent, _ = await _create_agent_with_key(
            db_session, name="hard-stop-events-agent", budget_monthly_cents=200
        )
        agent.spent_monthly_cents = 190
        await db_session.flush()

        svc = CostService(db_session)
        data = CostEventCreate(
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_cents=15,
        )
        await svc.record_cost(agent=agent, data=data)

        hard_stop_events = await _get_activity_events(db_session, "cost.hard_stop")
        budget_exceeded_events = await _get_activity_events(db_session, "agent.budget_exceeded")

        assert any(
            e.references and e.references.get("agent_id") == agent.id
            for e in hard_stop_events
        )
        assert any(
            e.references and e.references.get("agent_id") == agent.id
            for e in budget_exceeded_events
        )

    async def test_already_paused_agent_not_double_stopped(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Recording cost on an already-paused agent does not change status or emit duplicate events."""
        agent, _ = await _create_agent_with_key(
            db_session, name="paused-agent", budget_monthly_cents=100, status="paused"
        )
        agent.spent_monthly_cents = 200
        await db_session.flush()

        svc = CostService(db_session)
        data = CostEventCreate(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=10,
            output_tokens=5,
            cost_cents=5,
        )
        _, budget_status = await svc.record_cost(agent=agent, data=data)

        # hard_stop is True because spent >= budget, but agent was already paused
        assert budget_status.hard_stop_triggered is True
        await db_session.refresh(agent)
        assert agent.status == "paused"  # unchanged


# ---------------------------------------------------------------------------
# Budget PATCH endpoint
# ---------------------------------------------------------------------------


class TestBudgetPatchEndpoint:
    async def test_patch_budget(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH /v1/agents/{uuid}/budget updates budget_monthly_cents."""
        agent, _ = await _create_agent_with_key(
            db_session, name="budget-patch-agent", budget_monthly_cents=0
        )
        await db_session.commit()

        resp = await test_client.patch(
            f"/v1/agents/{agent.uuid}/budget",
            json={"budget_monthly_cents": 10000},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["budget_monthly_cents"] == 10000

    async def test_patch_budget_with_reset(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH /v1/agents/{uuid}/budget with reset_spent=True zeros out spent_monthly_cents."""
        agent, _ = await _create_agent_with_key(
            db_session, name="budget-reset-agent", budget_monthly_cents=5000
        )
        agent.spent_monthly_cents = 4500
        await db_session.commit()

        resp = await test_client.patch(
            f"/v1/agents/{agent.uuid}/budget",
            json={"budget_monthly_cents": 10000, "reset_spent": True},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["budget_monthly_cents"] == 10000
        assert data["spent_monthly_cents"] == 0


# ---------------------------------------------------------------------------
# Pause / resume endpoints
# ---------------------------------------------------------------------------


class TestPauseResumeEndpoints:
    async def test_pause_active_agent(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/agents/{uuid}/pause sets status to paused."""
        agent, _ = await _create_agent_with_key(
            db_session, name="pause-test-agent", status="active"
        )
        await db_session.commit()

        resp = await test_client.post(
            f"/v1/agents/{agent.uuid}/pause",
            json={"reason": "Phase 4 test"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "paused"

    async def test_resume_paused_agent(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/agents/{uuid}/resume sets status back to active."""
        agent, _ = await _create_agent_with_key(
            db_session, name="resume-test-agent", status="paused"
        )
        await db_session.commit()

        resp = await test_client.post(
            f"/v1/agents/{agent.uuid}/resume",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "active"

    async def test_resume_active_agent_returns_422(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/agents/{uuid}/resume on a non-paused agent returns 422."""
        agent, _ = await _create_agent_with_key(
            db_session, name="resume-active-agent", status="active"
        )
        await db_session.commit()

        resp = await test_client.post(
            f"/v1/agents/{agent.uuid}/resume",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_pause_terminated_agent_returns_422(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/agents/{uuid}/pause on terminated agent returns 422."""
        agent, _ = await _create_agent_with_key(
            db_session, name="pause-terminated-agent", status="terminated"
        )
        await db_session.commit()

        resp = await test_client.post(
            f"/v1/agents/{agent.uuid}/pause",
            json={},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Cost reporting endpoints
# ---------------------------------------------------------------------------


class TestCostReportingEndpoints:
    async def test_cost_summary_returns_aggregates(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/costs/summary returns instance-wide cost aggregates."""
        resp = await test_client.get(
            "/v1/costs/summary",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "total_cost_cents" in data
        assert "total_input_tokens" in data
        assert "total_output_tokens" in data

    async def test_cost_by_agent_after_recording(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        agent_with_key: tuple[AgentRegistration, str],
        agent_auth_headers: dict[str, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/costs/by-agent reflects cost events recorded via POST /v1/cost-events."""
        agent, _ = agent_with_key

        # Record a cost event
        cost_resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 1000,
                "output_tokens": 200,
                "cost_cents": 5,
            },
            headers=agent_auth_headers,
        )
        assert cost_resp.status_code == 201, cost_resp.text

        # Check by-agent breakdown
        resp = await test_client.get(
            "/v1/costs/by-agent",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()["data"]
        assert isinstance(rows, list)
        agent_row = next(
            (r for r in rows if r["agent_registration_id"] == agent.id), None
        )
        assert agent_row is not None, "Agent not found in cost breakdown"
        assert agent_row["total_cost_cents"] >= 5

    async def test_post_cost_event_returns_budget_status(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        agent_with_key: tuple[AgentRegistration, str],
        agent_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/cost-events response includes agent_budget block."""
        agent, _ = agent_with_key
        # Set a budget so the response includes meaningful budget status
        agent.budget_monthly_cents = 10000
        await db_session.commit()

        resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "input_tokens": 500,
                "output_tokens": 100,
                "cost_cents": 3,
            },
            headers=agent_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert "cost_event_id" in data
        assert "agent_budget" in data
        budget = data["agent_budget"]
        assert "monthly_cents" in budget
        assert "spent_cents" in budget
        assert "remaining_cents" in budget
        assert budget["hard_stop_triggered"] is False
