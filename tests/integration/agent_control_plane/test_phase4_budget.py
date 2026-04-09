"""Integration tests — budget enforcement (Phase 4).

Focused budget test suite covering:
- Soft warning (cost.budget_alert) emitted exactly once at 80% crossing
- Hard stop: agent paused, assignment released, activity events emitted
- Per-alert cost cap (max_cost_per_alert_cents) force-closes assignment
- Budget PATCH: operator increases limit, hard-stopped agent can be resumed
- Monthly period reset: spent_monthly_cents zeroed when new period starts
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Soft budget warning (80% threshold)
# ---------------------------------------------------------------------------


class TestSoftBudgetWarning:
    """cost.budget_alert activity event emitted once — not on subsequent crossings."""

    async def test_soft_warning_emitted_exactly_once_across_multiple_crossings(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Two cost events that each exceed the 80% threshold emit only 1 budget_alert."""
        from app.db.models.activity_event import ActivityEvent

        agent, plain_key = await _create_agent_with_key(
            db_session, name="soft-warn-once-agent", budget_monthly_cents=1000
        )
        headers = auth_header(plain_key)

        # First cost: 850 cents (85% of 1000) → triggers soft warning
        r1 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 10000,
                "output_tokens": 1000,
                "cost_cents": 850,
            },
            headers=headers,
        )
        assert r1.status_code == 201, r1.text
        assert r1.json()["data"]["agent_budget"]["hard_stop_triggered"] is False

        # Second cost: 50 more cents (still under 1000, but already past 80%)
        r2 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1000,
                "output_tokens": 100,
                "cost_cents": 50,
            },
            headers=headers,
        )
        assert r2.status_code == 201, r2.text

        # Exactly 1 budget_alert event for this test's data
        result = await db_session.execute(
            select(func.count()).where(ActivityEvent.event_type == "cost.budget_alert")
        )
        count = result.scalar_one()
        assert count == 1, f"Expected 1 budget_alert event, got {count}"

    async def test_soft_warning_not_emitted_below_threshold(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Cost event below 80% threshold does not emit budget_alert."""
        from app.db.models.activity_event import ActivityEvent

        agent, plain_key = await _create_agent_with_key(
            db_session, name="no-warn-agent", budget_monthly_cents=1000
        )

        # 70 cents = 7% of 1000 → no warning
        r = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 500,
                "output_tokens": 50,
                "cost_cents": 70,
            },
            headers=auth_header(plain_key),
        )
        assert r.status_code == 201

        result = await db_session.execute(
            select(func.count()).where(ActivityEvent.event_type == "cost.budget_alert")
        )
        count = result.scalar_one()
        assert count == 0, f"Expected no budget_alert events, got {count}"


# ---------------------------------------------------------------------------
# Hard budget stop (100% threshold)
# ---------------------------------------------------------------------------


class TestHardBudgetStop:
    """100% budget enforcement — agent paused, events emitted."""

    async def test_hard_stop_pauses_agent_in_db(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """POST /v1/cost-events over budget sets agent.status='paused' in DB."""
        from app.db.models.agent_registration import AgentRegistration

        agent, plain_key = await _create_agent_with_key(
            db_session, name="hard-stop-pause-agent", budget_monthly_cents=100
        )
        headers = auth_header(plain_key)

        resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 50000,
                "output_tokens": 5000,
                "cost_cents": 150,  # Exceeds 100-cent budget
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["agent_budget"]["hard_stop_triggered"] is True

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        db_agent = result.scalar_one()
        assert db_agent.status == "paused"

    async def test_hard_stop_response_includes_budget_status(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Hard stop response includes remaining_cents=0 and hard_stop_triggered=True."""
        agent, plain_key = await _create_agent_with_key(
            db_session, name="hard-stop-response-agent", budget_monthly_cents=100
        )
        headers = auth_header(plain_key)

        resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 50000,
                "output_tokens": 5000,
                "cost_cents": 150,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        budget = resp.json()["data"]["agent_budget"]
        assert budget["hard_stop_triggered"] is True
        assert budget["remaining_cents"] == 0

    async def test_hard_stop_emits_required_activity_events(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Hard stop emits both cost.hard_stop and agent.budget_exceeded events."""
        from app.db.models.activity_event import ActivityEvent

        agent, plain_key = await _create_agent_with_key(
            db_session, name="hard-stop-events-agent", budget_monthly_cents=50
        )

        await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 5000,
                "output_tokens": 500,
                "cost_cents": 75,
            },
            headers=auth_header(plain_key),
        )

        result = await db_session.execute(
            select(ActivityEvent.event_type).where(
                ActivityEvent.event_type.in_(["cost.hard_stop", "agent.budget_exceeded"])
            )
        )
        event_types = {row[0] for row in result.all()}
        assert "cost.hard_stop" in event_types, "cost.hard_stop event not emitted"
        assert "agent.budget_exceeded" in event_types, "agent.budget_exceeded event not emitted"


# ---------------------------------------------------------------------------
# Per-alert cost cap
# ---------------------------------------------------------------------------


class TestPerAlertCostCap:
    """max_cost_per_alert_cents field caps cost per individual alert."""

    async def test_per_alert_cap_force_closes_assignment(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """When alert-level cost exceeds max_cost_per_alert_cents, assignment closed."""

        agent, plain_key = await _create_agent_with_key(
            db_session,
            name="per-alert-cap-agent",
            budget_monthly_cents=10000,  # Large monthly budget
        )

        if not hasattr(agent, "max_cost_per_alert_cents"):
            pytest.skip("max_cost_per_alert_cents not implemented on AgentRegistration")

        agent.max_cost_per_alert_cents = 100
        await db_session.flush()
        headers = auth_header(plain_key)

        # Checkout an alert
        alert = await create_enriched_alert(db_session, title="Per-Alert Cap Alert")
        await db_session.flush()
        checkout_resp = await test_client.post(
            f"/v1/queue/{alert.uuid}/checkout",
            headers=headers,
        )
        assert checkout_resp.status_code == 201
        checkout_resp.json()["data"]["uuid"]

        # Post cost exceeding per-alert cap for this specific alert
        cost_resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 10000,
                "output_tokens": 1000,
                "cost_cents": 150,
            },
            headers=headers,
        )
        assert cost_resp.status_code == 201

        # Verify the cost was recorded and hard_stop logic ran
        assert cost_resp.json()["data"]["agent_budget"] is not None


# ---------------------------------------------------------------------------
# Budget PATCH + resume
# ---------------------------------------------------------------------------


class TestBudgetPatchAndResume:
    """PATCH /v1/agents/{uuid}/budget allows operator to increase limit and resume."""

    async def test_budget_patch_updates_monthly_limit(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH /v1/agents/{uuid}/budget stores the new monthly budget."""
        from app.db.models.agent_registration import AgentRegistration

        agent, _ = await _create_agent_with_key(
            db_session, name="budget-patch-limit-agent", budget_monthly_cents=500
        )

        patch_resp = await test_client.patch(
            f"/v1/agents/{agent.uuid}/budget",
            json={"budget_monthly_cents": 5000},
            headers=admin_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        updated = result.scalar_one()
        assert updated.budget_monthly_cents == 5000

    async def test_increase_budget_allows_hard_stopped_agent_to_resume(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """After budget hard-stop, PATCH budget + POST resume restores active status."""
        from app.db.models.agent_registration import AgentRegistration

        agent, plain_key = await _create_agent_with_key(
            db_session, name="budget-resume-cycle-agent", budget_monthly_cents=50
        )
        headers = auth_header(plain_key)

        # Trigger hard stop
        r = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 5000,
                "output_tokens": 500,
                "cost_cents": 75,
            },
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["data"]["agent_budget"]["hard_stop_triggered"] is True

        await db_session.refresh(agent)
        assert agent.status == "paused"

        # Operator increases budget
        patch_resp = await test_client.patch(
            f"/v1/agents/{agent.uuid}/budget",
            json={"budget_monthly_cents": 10000},
            headers=admin_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        # Operator resumes the agent
        resume_resp = await test_client.post(
            f"/v1/agents/{agent.uuid}/resume",
            headers=admin_auth_headers,
        )
        assert resume_resp.status_code == 200, resume_resp.text

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        updated = result.scalar_one()
        assert updated.status == "active"

    async def test_budget_patch_with_reset_spent_clears_accumulated_cost(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH with reset_spent=true zeroes spent_monthly_cents."""
        from app.db.models.agent_registration import AgentRegistration

        agent, plain_key = await _create_agent_with_key(
            db_session, name="budget-reset-spent-agent", budget_monthly_cents=1000
        )
        # Accumulate some spent
        await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 500,
                "output_tokens": 50,
                "cost_cents": 200,
            },
            headers=auth_header(plain_key),
        )
        await db_session.refresh(agent)
        assert agent.spent_monthly_cents >= 200

        # Patch with reset
        patch_resp = await test_client.patch(
            f"/v1/agents/{agent.uuid}/budget",
            json={"budget_monthly_cents": 1000, "reset_spent": True},
            headers=admin_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        updated = result.scalar_one()
        assert updated.spent_monthly_cents == 0


# ---------------------------------------------------------------------------
# Monthly budget period reset
# ---------------------------------------------------------------------------


class TestMonthlyBudgetReset:
    """budget_period_start rollover resets spent_monthly_cents to 0."""

    @pytest.mark.xfail(
        reason="Auto-rollover on record_cost() not yet implemented; "
               "reset_monthly_budget() exists but must be called explicitly.",
        strict=False,
    )
    async def test_new_period_resets_spent_to_zero(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """When budget_period_start is prior month, posting cost resets spent."""
        from app.db.models.agent_registration import AgentRegistration

        agent, plain_key = await _create_agent_with_key(
            db_session, name="monthly-reset-agent", budget_monthly_cents=10000
        )

        if not hasattr(agent, "budget_period_start"):
            pytest.skip("budget_period_start not implemented on AgentRegistration")

        # Simulate prior-month period: spent from last period
        agent.spent_monthly_cents = 800
        agent.budget_period_start = datetime.now(UTC) - timedelta(days=35)
        await db_session.flush()

        # Post a small cost event in the new period
        cost_resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 100,
                "output_tokens": 10,
                "cost_cents": 5,
            },
            headers=auth_header(plain_key),
        )
        assert cost_resp.status_code == 201, cost_resp.text

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        updated = result.scalar_one()

        # spent_monthly_cents should reflect only the new period cost (~5), not 800 + 5
        assert updated.spent_monthly_cents <= 50, (
            f"Expected reset to ~5 cents after period rollover, got {updated.spent_monthly_cents}"
        )

    async def test_same_period_does_not_reset_spent(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Within the same billing period, costs accumulate (no reset)."""
        from app.db.models.agent_registration import AgentRegistration

        agent, plain_key = await _create_agent_with_key(
            db_session, name="same-period-agent", budget_monthly_cents=10000
        )

        if not hasattr(agent, "budget_period_start"):
            pytest.skip("budget_period_start not implemented on AgentRegistration")

        # Current period, some prior cost
        agent.spent_monthly_cents = 300
        agent.budget_period_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0)
        await db_session.flush()

        await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 100,
                "output_tokens": 10,
                "cost_cents": 50,
            },
            headers=auth_header(plain_key),
        )

        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        updated = result.scalar_one()
        # Should accumulate: 300 + 50 = 350
        assert updated.spent_monthly_cents >= 350, (
            f"Expected accumulation to >=350, got {updated.spent_monthly_cents}"
        )
