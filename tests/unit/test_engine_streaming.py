"""Unit tests for engine streaming event emission."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.base import CostInfo, LLMResponse
from app.runtime.engine import AgentRuntimeEngine
from app.runtime.models import RuntimeContext


def _make_llm_response(
    content_blocks: list[dict],
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> LLMResponse:
    """Build a mock LLMResponse."""
    return LLMResponse(
        content=content_blocks,
        stop_reason=stop_reason,
        usage=CostInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_cents=1,
            billing_type="api",
        ),
    )


@pytest.mark.asyncio
class TestEngineOnLogPassthrough:
    """Verify on_log is passed to adapter.create_message."""

    async def test_on_log_passed_to_adapter(self) -> None:
        """The tool loop passes on_log to adapter.create_message."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        # Mock adapter that records on_log argument
        adapter = AsyncMock()
        adapter.create_message.return_value = _make_llm_response(
            [{"type": "text", "text": "Done."}],
        )

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096
        agent.max_cost_per_alert_cents = 0
        agent.tool_ids = []

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        on_log = AsyncMock()

        with (
            patch(
                "app.services.run_cancellation.is_cancelled",
                return_value=False,
            ),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                system="system prompt",
                agent=agent,
                context=context,
                integration=MagicMock(),
                on_log=on_log,
            )

        # Verify on_log was passed to adapter
        call_kwargs = adapter.create_message.call_args
        assert call_kwargs.kwargs.get("on_log") is on_log


@pytest.mark.asyncio
class TestEngineToolEventEmission:
    """Verify engine emits tool_call and tool_result events."""

    async def test_tool_call_and_result_events_emitted(self) -> None:
        """When adapter returns tool_use, engine emits tool_call and tool_result via on_log."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        # First response: tool_use, second response: end_turn
        responses = [
            _make_llm_response(
                [{"type": "tool_use", "id": "t1", "name": "search_alerts", "input": {"query": "test"}}],
                stop_reason="tool_use",
            ),
            _make_llm_response(
                [{"type": "text", "text": "Found 3 alerts."}],
            ),
        ]
        adapter = AsyncMock()
        adapter.create_message.side_effect = responses

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096
        agent.max_cost_per_alert_cents = 0

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        on_log = AsyncMock()

        # Mock the tool dispatcher
        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch.return_value = {"data": {"count": 3}}

        with (
            patch(
                "app.services.run_cancellation.is_cancelled",
                return_value=False,
            ),
            patch(
                "app.runtime.engine.ToolDispatcher",
                return_value=mock_dispatcher,
            ),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[{"name": "search_alerts"}],
                system="system",
                agent=agent,
                context=context,
                integration=MagicMock(),
                on_log=on_log,
            )

        # Check that on_log was called with tool_call and tool_result
        call_streams = [call.args[0] for call in on_log.call_args_list]
        assert "tool_call" in call_streams
        assert "tool_result" in call_streams


@pytest.mark.asyncio
class TestEngineBudgetCheckEvent:
    """Verify budget_check events are emitted."""

    async def test_budget_check_event_emitted(self) -> None:
        """on_log receives budget_check when budget tracking is active."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        adapter = AsyncMock()
        adapter.create_message.return_value = _make_llm_response(
            [{"type": "text", "text": "Done."}],
        )

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096
        agent.max_cost_per_alert_cents = 100  # Budget set

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        on_log = AsyncMock()

        with (
            patch(
                "app.services.run_cancellation.is_cancelled",
                return_value=False,
            ),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                system="system",
                agent=agent,
                context=context,
                integration=MagicMock(),
                on_log=on_log,
            )

        call_streams = [call.args[0] for call in on_log.call_args_list]
        assert "budget_check" in call_streams


@pytest.mark.asyncio
class TestEngineBudgetCheckEventNoBudget:
    """Verify budget_check events are emitted even when budget is zero (disabled)."""

    async def test_budget_check_emitted_when_budget_zero(self) -> None:
        """budget_check event is emitted regardless of max_cost_per_alert_cents value."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        adapter = AsyncMock()
        adapter.create_message.return_value = _make_llm_response(
            [{"type": "text", "text": "Done."}],
        )

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096
        agent.max_cost_per_alert_cents = 0  # No budget limit

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        on_log = AsyncMock()

        with (
            patch(
                "app.services.run_cancellation.is_cancelled",
                return_value=False,
            ),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                system="system",
                agent=agent,
                context=context,
                integration=MagicMock(),
                on_log=on_log,
            )

        call_streams = [call.args[0] for call in on_log.call_args_list]
        assert "budget_check" in call_streams


@pytest.mark.asyncio
class TestEngineCancellationCheck:
    """Verify cancellation flag is checked in the loop."""

    async def test_cancelled_run_returns_early(self) -> None:
        """When is_cancelled returns True, loop exits immediately."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        adapter = AsyncMock()
        # Should never be called
        adapter.create_message.side_effect = AssertionError(
            "LLM should not be called after cancellation",
        )

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        with patch(
            "app.services.run_cancellation.is_cancelled",
            return_value=True,
        ):
            messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                system="system",
                agent=agent,
                context=context,
                integration=MagicMock(),
            )

        assert result.success is False
        assert "cancelled" in (result.error or "").lower()
        adapter.create_message.assert_not_called()


@pytest.mark.asyncio
class TestEngineFindingEvent:
    """Verify finding events are emitted when tool returns a finding."""

    async def test_finding_event_emitted(self) -> None:
        """on_log receives finding event when tool result contains a finding key."""
        db = AsyncMock()
        engine = AgentRuntimeEngine(db)

        finding_data = {"classification": "malicious", "confidence": 0.95}

        responses = [
            _make_llm_response(
                [{"type": "tool_use", "id": "t1", "name": "post_finding", "input": {"alert_uuid": "abc"}}],
                stop_reason="tool_use",
            ),
            _make_llm_response(
                [{"type": "text", "text": "Finding posted."}],
            ),
        ]
        adapter = AsyncMock()
        adapter.create_message.side_effect = responses

        agent = MagicMock()
        agent.id = 1
        agent.max_tokens = 4096
        agent.max_cost_per_alert_cents = 0

        context = RuntimeContext(
            agent_id=1,
            task_key="alert:1",
            heartbeat_run_id=1,
        )

        on_log = AsyncMock()

        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch.return_value = {"finding": finding_data}

        with (
            patch(
                "app.services.run_cancellation.is_cancelled",
                return_value=False,
            ),
            patch(
                "app.runtime.engine.ToolDispatcher",
                return_value=mock_dispatcher,
            ),
            patch.object(engine, "_record_cost", new_callable=AsyncMock),
        ):
            _messages, result = await engine._run_tool_loop(
                adapter=adapter,
                messages=[{"role": "user", "content": "test"}],
                tools=[{"name": "post_finding"}],
                system="system",
                agent=agent,
                context=context,
                integration=MagicMock(),
                on_log=on_log,
            )

        call_streams = [call.args[0] for call in on_log.call_args_list]
        assert "finding" in call_streams

        # Verify the finding data was included in the on_log payload
        finding_calls = [
            call for call in on_log.call_args_list if call.args[0] == "finding"
        ]
        assert len(finding_calls) >= 1
        finding_json = finding_calls[0].args[1]
        parsed = json.loads(finding_json)
        assert parsed["classification"] == "malicious"

        # Verify finding was accumulated in result
        assert len(result.findings) == 1
        assert result.findings[0]["classification"] == "malicious"
