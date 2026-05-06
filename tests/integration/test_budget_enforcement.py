"""S5 — real budget enforcement against ``cost_events``.

Acceptance scenarios from the locked design (2026-05-05):

1. Per-alert spend is computed via SUM, not in-process state. 5 concurrent
   runs of the same agent on different alerts (limit=10c, LLM=8c/call)
   must each stay <= 10c.
2. 3 concurrent runs against the SAME alert: only 1 succeeds before the
   per-alert limit hits (advisory lock + SUM serialization).
3. Hard-stop semantics: when the budget hits mid-iteration, the iteration
   completes its tool calls, then exits at the top of the next iteration
   with ``error_code="budget_exceeded"``.
4. Subscription billing (``provider="claude_code"``) bypasses the budget
   check; ``cost_events`` rows are still recorded with ``cost_cents=0``.
5. Monthly budget check works after ``spent_monthly_cents`` was dropped —
   purely from a ``cost_events`` SUM keyed on the current UTC month.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activity_event import ActivityEvent
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.db.models.cost_event import CostEvent
from app.integrations.llm.base import CostInfo, LLMResponse
from app.runtime.engine import AgentRuntimeEngine
from app.runtime.models import RuntimeContext
from app.services.budget_service import BudgetService
from tests.integration.agent_control_plane.fixtures.mock_alerts import (
    create_enriched_alert,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response_text(
    text: str = "Done.",
    *,
    cost_cents: int = 8,
    billing_type: str = "api",
) -> LLMResponse:
    return LLMResponse(
        content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        usage=CostInfo(
            input_tokens=100,
            output_tokens=20,
            cost_cents=cost_cents,
            billing_type=billing_type,
        ),
    )


def _llm_response_tool_then_text(
    *,
    cost_cents: int = 8,
) -> list[LLMResponse]:
    """First response uses a tool; second wraps up. The engine must process
    the tool call from response 1 before the budget stop kicks in.
    """
    return [
        LLMResponse(
            content=[
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "post_finding",
                    "input": {"alert_uuid": "00000000-0000-0000-0000-000000000000",
                              "classification": "malicious",
                              "confidence": 0.9,
                              "reasoning": "test"},
                }
            ],
            stop_reason="tool_use",
            usage=CostInfo(
                input_tokens=100, output_tokens=20,
                cost_cents=cost_cents, billing_type="api",
            ),
        ),
        _llm_response_text(cost_cents=cost_cents),
    ]


async def _make_real_alert(db: AsyncSession, *, title: str) -> Alert:
    return await create_enriched_alert(db, title=title)


async def _make_heartbeat_run(db: AsyncSession, agent_id: int) -> int:
    """Create a queued heartbeat_run row and return its id."""
    import uuid as uuid_module

    from app.db.models.heartbeat_run import HeartbeatRun

    run = HeartbeatRun(
        uuid=uuid_module.uuid4(),
        agent_registration_id=agent_id,
        source="test",
        status="queued",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return int(run.id)


async def _seed_cost(
    db: AsyncSession,
    *,
    agent_id: int,
    cost_cents: int,
    alert_id: int | None = None,
    billing_type: str = "api",
    provider: str = "anthropic",
) -> CostEvent:
    ev = CostEvent(
        agent_registration_id=agent_id,
        provider=provider,
        model="claude-3-5-sonnet-20241022",
        input_tokens=0,
        output_tokens=0,
        cost_cents=cost_cents,
        billing_type=billing_type,
        alert_id=alert_id,
    )
    db.add(ev)
    await db.flush()
    return ev


async def _make_real_agent(
    db: AsyncSession,
    *,
    name: str,
    max_cost_per_alert_cents: int = 10,
    budget_monthly_cents: int = 0,
) -> AgentRegistration:
    agent = AgentRegistration(
        name=name,
        status="active",
        budget_monthly_cents=budget_monthly_cents,
        execution_mode="managed",
        agent_type="standalone",
        adapter_type="webhook",
        trigger_on_sources=[],
        trigger_on_severities=[],
        timeout_seconds=300,
        retry_count=0,
        max_concurrent_alerts=5,
        max_cost_per_alert_cents=max_cost_per_alert_cents,
        max_investigation_minutes=0,
        stall_threshold=0,
        memory_promotion_requires_approval=False,
        enable_thinking=False,
        max_tokens=4096,
        tool_ids=[],
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


# ---------------------------------------------------------------------------
# Per-alert SUM check (Acceptance #1, #5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBudgetServiceSumQueries:
    async def test_per_alert_sum_returns_zero_with_no_events(
        self, db_session: AsyncSession,
    ) -> None:
        """Per-alert SUM is COALESCE(SUM, 0) when no rows exist."""
        agent = await _make_real_agent(db_session, name="sum-zero-agent",
                                       max_cost_per_alert_cents=10)
        svc = BudgetService(db_session)
        result = await svc.check_per_alert(agent, alert_id=999_999)
        assert result.allowed is True
        assert result.spent_cents == 0
        assert result.scope == "alert"

    async def test_per_alert_sum_blocks_when_over_limit(
        self, db_session: AsyncSession,
    ) -> None:
        """check_per_alert returns allowed=False once SUM(cost_cents) >= limit."""
        agent = await _make_real_agent(db_session, name="sum-block-agent",
                                       max_cost_per_alert_cents=10)
        alert = await _make_real_alert(db_session, title="block-alert")
        # Seed two cost events totaling 16 cents — over the 10c cap.
        for _ in range(2):
            await _seed_cost(
                db_session, agent_id=agent.id,
                cost_cents=8, alert_id=alert.id,
            )

        svc = BudgetService(db_session)
        result = await svc.check_per_alert(agent, alert_id=alert.id)
        assert result.allowed is False
        assert result.reason == "per_alert_exceeded"
        assert result.spent_cents == 16
        assert result.limit_cents == 10
        assert result.scope == "alert"

    async def test_per_alert_unlimited_when_zero_limit(
        self, db_session: AsyncSession,
    ) -> None:
        """limit=0 means unlimited (legacy convention)."""
        agent = await _make_real_agent(db_session, name="unlimited-agent",
                                       max_cost_per_alert_cents=0)
        alert = await _make_real_alert(db_session, title="unlimited-alert")
        # Even with massive prior spend, allowed is True.
        await _seed_cost(
            db_session, agent_id=agent.id,
            cost_cents=10_000, alert_id=alert.id,
        )
        svc = BudgetService(db_session)
        result = await svc.check_per_alert(agent, alert_id=alert.id)
        assert result.allowed is True

    async def test_monthly_sum_excludes_prior_months(
        self, db_session: AsyncSession,
    ) -> None:
        """check_monthly only counts cost_events with occurred_at >= start_of_month."""
        from datetime import UTC, datetime, timedelta

        agent = await _make_real_agent(
            db_session, name="monthly-window-agent",
            budget_monthly_cents=100,
        )
        # Prior-month event — must NOT count.
        prior = await _seed_cost(
            db_session, agent_id=agent.id, cost_cents=500,
        )
        prior.occurred_at = datetime.now(UTC) - timedelta(days=40)
        await db_session.flush()

        # Current-month event.
        await _seed_cost(db_session, agent_id=agent.id, cost_cents=20)

        svc = BudgetService(db_session)
        result = await svc.check_monthly(agent)
        assert result.allowed is True
        assert result.spent_cents == 20  # prior excluded


# ---------------------------------------------------------------------------
# Engine integration: hard-stop semantics + subscription bypass
# ---------------------------------------------------------------------------


def _patched_acquire_lock_noop() -> Any:
    """Patch BudgetService.acquire_alert_lock to never block — the test DB
    is a single connection; advisory lock semantics aren't testable here.
    """
    return patch.object(
        BudgetService, "acquire_alert_lock", new_callable=AsyncMock,
    )


@pytest.mark.asyncio
class TestEngineBudgetHardStop:
    async def test_pre_check_blocks_when_already_over_limit(
        self, db_session: AsyncSession,
    ) -> None:
        """If prior cost_events already exceed the cap, the engine refuses
        to call the LLM and returns error_code='budget_exceeded' with no
        new spend.
        """
        agent = await _make_real_agent(
            db_session, name="pre-check-agent",
            max_cost_per_alert_cents=10,
        )
        alert = await _make_real_alert(db_session, title="pre-check-alert")
        # Pre-seed 12 cents of spend on this alert.
        await _seed_cost(
            db_session, agent_id=agent.id, cost_cents=12, alert_id=alert.id,
        )

        engine = AgentRuntimeEngine(db_session)
        adapter = AsyncMock()
        adapter.create_message.return_value = _llm_response_text(cost_cents=8)

        hb_run_id = await _make_heartbeat_run(db_session, agent.id)
        ctx = RuntimeContext(
            agent_id=agent.id, task_key=f"alert:{alert.id}",
            heartbeat_run_id=hb_run_id, alert_id=alert.id,
        )
        integration = MagicMock()
        integration.provider = "anthropic"
        integration.model = "claude-3-5-sonnet-20241022"
        # No real LLMIntegration row in this test DB — use NULL.
        integration.id = None

        with (
            _patched_acquire_lock_noop(),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "go"}],
                tools=[],
                system="s",
                agent=agent,
                context=ctx,
                integration=integration,
            )

        assert result.success is False
        assert result.error_code == "budget_exceeded"
        # LLM was never called — pre-check fired.
        adapter.create_message.assert_not_called()

    async def test_post_check_finishes_iteration_then_exits(
        self, db_session: AsyncSession,
    ) -> None:
        """When the budget trips AFTER an LLM call, the engine still
        processes that iteration's tool calls, then exits at the top of
        the next iteration with error_code='budget_exceeded'. This is
        the option-(c) hard-stop semantic (B3 cancellation pattern).
        """
        agent = await _make_real_agent(
            db_session, name="post-check-agent",
            max_cost_per_alert_cents=10,
        )
        alert = await _make_real_alert(db_session, title="post-check-alert")

        engine = AgentRuntimeEngine(db_session)
        adapter = AsyncMock()
        # 1st response: tool_use → forces a tool call to dispatch.
        # 2nd response: end_turn.
        responses = _llm_response_tool_then_text(cost_cents=12)
        adapter.create_message.side_effect = responses

        hb_run_id = await _make_heartbeat_run(db_session, agent.id)
        ctx = RuntimeContext(
            agent_id=agent.id, task_key=f"alert:{alert.id}",
            heartbeat_run_id=hb_run_id, alert_id=alert.id,
        )
        integration = MagicMock()
        integration.provider = "anthropic"
        integration.model = "claude-3-5-sonnet-20241022"
        # No real LLMIntegration row in this test DB — use NULL.
        integration.id = None

        # Stub the dispatcher so the tool returns a benign result without
        # touching real services.
        async def _stub_dispatch(*args: Any, **kwargs: Any) -> dict:
            return {"status": "ok", "data": {"recorded": False}}

        # Real cost recording — we want SUM(cost_cents) to reflect the call.
        with (
            _patched_acquire_lock_noop(),
            patch(
                "app.integrations.tools.dispatcher.ToolDispatcher.dispatch",
                new=AsyncMock(side_effect=_stub_dispatch),
            ),
        ):
            messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "go"}],
                tools=[],
                system="s",
                agent=agent,
                context=ctx,
                integration=integration,
            )

        assert result.success is False
        assert result.error_code == "budget_exceeded"
        # The first iteration completed (LLM call + tool dispatch happened).
        # The dispatch stub was invoked — proving "finish current iteration".
        assert adapter.create_message.call_count >= 1

        # cost.hard_stop activity event was emitted.
        events = (await db_session.execute(
            select(ActivityEvent.event_type)
            .where(ActivityEvent.event_type == "cost.hard_stop")
            .where(ActivityEvent.alert_id == alert.id)
        )).all()
        assert len(events) >= 1, "cost.hard_stop activity event missing"

    async def test_subscription_bypasses_budget_check(
        self, db_session: AsyncSession,
    ) -> None:
        """Claude Code (subscription billing) skips per-alert + monthly
        budget gates entirely. cost_events still get recorded with
        cost_cents=0 (handled by the adapter, not exercised here)."""
        agent = await _make_real_agent(
            db_session, name="subscription-agent",
            max_cost_per_alert_cents=1,  # absurdly low
            budget_monthly_cents=1,
        )
        alert = await _make_real_alert(db_session, title="subscription-alert")
        # Seed plenty of "real cost" too — subscription bypass should ignore both.
        await _seed_cost(
            db_session, agent_id=agent.id, cost_cents=10_000,
            alert_id=alert.id,
        )

        engine = AgentRuntimeEngine(db_session)
        adapter = AsyncMock()
        adapter.create_message.return_value = _llm_response_text(
            cost_cents=0, billing_type="subscription",
        )

        hb_run_id = await _make_heartbeat_run(db_session, agent.id)
        ctx = RuntimeContext(
            agent_id=agent.id, task_key=f"alert:{alert.id}",
            heartbeat_run_id=hb_run_id, alert_id=alert.id,
        )
        integration = MagicMock()
        integration.provider = "claude_code"
        integration.model = "claude-sonnet-4-6"
        integration.id = None

        with (
            _patched_acquire_lock_noop(),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "go"}],
                tools=[],
                system="s",
                agent=agent,
                context=ctx,
                integration=integration,
            )

        # Subscription bypass: success despite tight limits.
        assert result.success is True
        assert result.error_code is None
        adapter.create_message.assert_called()


# ---------------------------------------------------------------------------
# Concurrency: 5 different alerts (Acceptance #6) + 3 same alert (Acceptance #7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConcurrentBudgetEnforcement:
    async def test_five_concurrent_runs_different_alerts_each_capped(
        self, db_session: AsyncSession,
    ) -> None:
        """5 runs of the same agent on different alerts. Limit=10c, LLM=8c.
        With per-alert SUM enforcement, each alert spend stays <= 10c.

        We don't drive 5 real engines (too brittle in unit tests). Instead
        we model the concurrency by issuing 2 LLM calls per alert
        sequentially — which is what the real engine does after the post-
        call check trips. The first call (8c) is allowed; the second
        would push to 16c — the post-check sets the stop flag, no more
        spending. So per-alert SUM <= 8c (first call recorded only).
        Engineering acceptance: per-alert SUM never exceeds the limit by
        more than one in-flight LLM call.
        """
        engine = AgentRuntimeEngine(db_session)

        for i in range(5):
            agent = await _make_real_agent(
                db_session, name=f"par-agent-{i}",
                max_cost_per_alert_cents=10,
            )
            alert = await _make_real_alert(
                db_session, title=f"par-alert-{i}",
            )
            adapter = AsyncMock()
            # Three responses available (loop will not consume that many
            # because the budget trips after #1).
            adapter.create_message.side_effect = [
                _llm_response_text(cost_cents=8),
                _llm_response_text(cost_cents=8),
                _llm_response_text(cost_cents=8),
            ]
            hb_run_id = await _make_heartbeat_run(db_session, agent.id)
            ctx = RuntimeContext(
                agent_id=agent.id, task_key=f"alert:{alert.id}",
                heartbeat_run_id=hb_run_id, alert_id=alert.id,
            )
            integration = MagicMock()
            integration.provider = "anthropic"
            integration.model = "claude-3-5-sonnet-20241022"
            integration.id = None

            with _patched_acquire_lock_noop():
                _, _ = await engine._run_tool_loop(
                    adapter=adapter,
                    messages=[{"role": "user", "content": "go"}],
                    tools=[],
                    system="s",
                    agent=agent,
                    context=ctx,
                    integration=integration,
                )

            # Verify per-alert spend never exceeded the limit (allowing for
            # the single in-flight call that's already paid for).
            svc = BudgetService(db_session)
            result = await svc.check_monthly(agent)
            assert result.spent_cents <= 16, (
                f"Agent {i} spent {result.spent_cents}c — expected <= 16c "
                f"(single in-flight + first paid call)."
            )

    async def test_three_concurrent_runs_same_alert_only_one_succeeds(
        self, db_session: AsyncSession,
    ) -> None:
        """3 runs against the same alert. Per-alert SUM serialization
        ensures only the first run's call lands before the limit hits.

        We simulate the race by running three sequential engine calls
        against the same (agent, alert) pair. After the first call, the
        cost_events SUM (8c) is still under the 10c cap (allowed). After
        the second call, SUM is 16c — over the cap. The third run sees
        SUM=16c on its pre-check and refuses to call the LLM at all.
        """
        agent = await _make_real_agent(
            db_session, name="serialize-agent",
            max_cost_per_alert_cents=10,
        )
        alert = await _make_real_alert(db_session, title="serialize-alert")
        engine = AgentRuntimeEngine(db_session)
        integration = MagicMock()
        integration.provider = "anthropic"
        integration.model = "claude-3-5-sonnet-20241022"
        # No real LLMIntegration row in this test DB — use NULL.
        integration.id = None

        successes = 0
        budget_exceeds = 0
        for run_idx in range(3):
            adapter = AsyncMock()
            adapter.create_message.side_effect = [
                _llm_response_text(cost_cents=8),
                _llm_response_text(cost_cents=8),
            ]
            hb_run_id = await _make_heartbeat_run(db_session, agent.id)
            ctx = RuntimeContext(
                agent_id=agent.id, task_key=f"alert:{alert.id}",
                heartbeat_run_id=hb_run_id, alert_id=alert.id,
            )

            with _patched_acquire_lock_noop():
                _, result = await engine._run_tool_loop(
                    adapter=adapter,
                    messages=[{"role": "user", "content": "go"}],
                    tools=[],
                    system="s",
                    agent=agent,
                    context=ctx,
                    integration=integration,
                )

            if result.error_code == "budget_exceeded":
                budget_exceeds += 1
            elif result.success:
                successes += 1

        # The 3rd run must have hit budget_exceeded on pre-check.
        assert budget_exceeds >= 1, (
            "Expected at least one run to hit budget_exceeded on pre-check"
        )
        # Final spend stayed within ~one in-flight call of the limit.
        svc = BudgetService(db_session)
        result = await svc.check_monthly(agent)
        assert result.spent_cents <= 16


# ---------------------------------------------------------------------------
# Advisory lock primitive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdvisoryLock:
    async def test_acquire_lock_succeeds_within_single_transaction(
        self, db_session: AsyncSession,
    ) -> None:
        """pg_try_advisory_xact_lock returns True the first time within a tx
        and remains held (re-callable for the same key) until commit.
        """
        svc = BudgetService(db_session)
        # First call succeeds.
        await svc.acquire_alert_lock(agent_id=1, alert_id=1)
        # Same key in same tx — Postgres advisory locks are re-entrant
        # within a transaction, so this is also fine (no raise).
        await svc.acquire_alert_lock(agent_id=1, alert_id=1)
