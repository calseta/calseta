"""Unit tests for PromptBuilder session resume optimization — C3: Session Resume."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime.models import RuntimeContext
from app.runtime.prompt_builder import PromptBuilder, _estimate_tokens


def _make_builder() -> PromptBuilder:
    """Create a PromptBuilder with a mock DB session."""
    db = AsyncMock()
    return PromptBuilder(db)


def _make_context(**overrides) -> RuntimeContext:
    """Create a RuntimeContext with sensible defaults."""
    defaults = {
        "agent_id": 1,
        "task_key": "alert:42",
        "heartbeat_run_id": 100,
        "alert_id": 42,
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


def _make_agent(**overrides):
    """Create a mock AgentRegistration with sensible defaults."""
    agent = MagicMock()
    agent.id = overrides.get("id", 1)
    agent.uuid = overrides.get("uuid", "550e8400-e29b-41d4-a716-446655440000")
    agent.max_tokens = overrides.get("max_tokens", 100_000)
    agent.system_prompt = overrides.get("system_prompt", "You are a security analyst agent.")
    agent.methodology = overrides.get("methodology", "1. Triage\n2. Investigate\n3. Respond")
    agent.instruction_files = overrides.get("instruction_files")
    agent.role = overrides.get("role", "analyst")
    agent.budget_monthly_cents = overrides.get("budget_monthly_cents", 10000)
    agent.spent_monthly_cents = overrides.get("spent_monthly_cents", 500)
    return agent


def _make_session(*, messages=None, handoff=None, updated_at=None):
    """Create a mock AgentTaskSession."""
    session = MagicMock()
    params: dict = {}
    if messages is not None:
        params["messages"] = messages
    if handoff is not None:
        params["session_handoff_markdown"] = handoff
    session.session_params = params
    session.updated_at = updated_at or datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)
    return session


class TestFreshSession:
    """Tests for fresh sessions (no existing messages)."""

    async def test_fresh_session_includes_all_layers(self) -> None:
        """Fresh session (no messages) -> layers 1, 2, 3, 4, 6 all included."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="LAYER1_SYSTEM_PROMPT",
            ) as mock_l1,
            patch.object(
                builder, "_build_layer2",
                return_value="<methodology>LAYER2</methodology>",
            ) as mock_l2,
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("LAYER3_KB", 100),
            ) as mock_l3,
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value="LAYER4_ALERT",
            ) as mock_l4,
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="LAYER6_CHECKPOINT",
            ) as mock_l6,
        ):
            result = await builder.build(agent, ctx, session=None)

        # All layers should have been called
        mock_l1.assert_awaited_once_with(agent)
        mock_l2.assert_called_once_with(agent)
        mock_l3.assert_awaited_once()
        # Layer 3 should NOT have updated_since on fresh session
        l3_kwargs = mock_l3.call_args[1] if mock_l3.call_args[1] else {}
        assert l3_kwargs.get("updated_since") is None
        mock_l4.assert_awaited_once_with(ctx)
        mock_l6.assert_awaited_once()

        # System prompt should contain all layers
        assert "LAYER1_SYSTEM_PROMPT" in result.system_prompt
        assert "LAYER2" in result.system_prompt
        assert "LAYER3_KB" in result.system_prompt
        assert "LAYER6_CHECKPOINT" in result.system_prompt

        # Layer tokens should all be non-zero
        assert result.layer_tokens["layer1_system"] > 0
        assert result.layer_tokens["layer2_methodology"] > 0
        assert result.layer_tokens["layer3_kb"] == 100


class TestResumeSession:
    """Tests for session resume (existing messages or handoff)."""

    async def test_resume_skips_layer1_and_layer2(self) -> None:
        """Resume session (has messages) -> layers 1, 2 skipped, layer 6 included."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()
        session = _make_session(
            messages=[{"role": "user", "content": "previous context"}],
        )

        # _estimate_tokens("") returns 1 due to max(1, ...) floor
        empty_token_estimate = _estimate_tokens("")

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="LAYER1_FULL_CONTENT",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="LAYER2_FULL_CONTENT",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value="LAYER4_ALERT",
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="LAYER6_CHECKPOINT",
            ),
        ):
            result = await builder.build(agent, ctx, session=session)

        # On resume, layer1 and layer2 are set to "" — they should NOT contain
        # the full content in the system prompt
        assert "LAYER1_FULL_CONTENT" not in result.system_prompt
        assert "LAYER2_FULL_CONTENT" not in result.system_prompt

        # Layer tokens for skipped layers = _estimate_tokens("") which is 1
        # (the floor from max(1, 0//4))
        assert result.layer_tokens["layer1_system"] == empty_token_estimate
        assert result.layer_tokens["layer2_methodology"] == empty_token_estimate

        # Layer 6 should still be included
        assert "LAYER6_CHECKPOINT" in result.system_prompt

    async def test_resume_layer3_kb_uses_updated_since(self) -> None:
        """Resume session -> layer 3 KB gets updated_since=session.updated_at."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()
        session_time = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)
        session = _make_session(
            messages=[{"role": "user", "content": "previous"}],
            updated_at=session_time,
        )

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="L1",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="L2",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("updated_kb_content", 50),
            ) as mock_l3,
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
        ):
            await builder.build(agent, ctx, session=session)

        # Layer 3 should have been called with updated_since=session.updated_at
        mock_l3.assert_awaited_once()
        call_kwargs = mock_l3.call_args[1]
        assert call_kwargs["updated_since"] == session_time

    async def test_resume_layer_tokens_minimal_for_skipped(self) -> None:
        """Resume session -> layer_tokens for layer1/layer2 are minimal (empty string floor).

        _estimate_tokens("") returns 1 due to max(1, ...) floor. This is far less
        than the full layer content would cost.
        """
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()
        session = _make_session(
            messages=[{"role": "user", "content": "hello"}],
        )

        empty_token_estimate = _estimate_tokens("")
        full_l1 = "big system prompt that would cost many tokens"
        full_l2 = "methodology text with detailed steps"

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value=full_l1,
            ),
            patch.object(
                builder, "_build_layer2",
                return_value=full_l2,
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="checkpoint",
            ),
        ):
            result = await builder.build(agent, ctx, session=session)

        # On resume, layers are empty strings -> minimal token estimate
        assert result.layer_tokens["layer1_system"] == empty_token_estimate
        assert result.layer_tokens["layer2_methodology"] == empty_token_estimate
        # Verify this is far less than the full content would cost
        assert result.layer_tokens["layer1_system"] < _estimate_tokens(full_l1)
        assert result.layer_tokens["layer2_methodology"] < _estimate_tokens(full_l2)

    async def test_resume_with_handoff_markdown_detected_as_resume(self) -> None:
        """session_handoff_markdown present -> detected as resume, layers 1-2 skipped."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()
        session = _make_session(
            handoff="## Previous session summary\nAgent triaged alert 42...",
        )

        empty_token_estimate = _estimate_tokens("")

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="L1 content",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="L2 content",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value="alert context",
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
        ):
            result = await builder.build(agent, ctx, session=session)

        # Layers 1 and 2 content should not appear in system prompt
        assert "L1 content" not in result.system_prompt
        assert "L2 content" not in result.system_prompt
        # Layer tokens should be minimal (empty string floor)
        assert result.layer_tokens["layer1_system"] == empty_token_estimate
        assert result.layer_tokens["layer2_methodology"] == empty_token_estimate

    async def test_resume_logs_token_savings(self) -> None:
        """Resume session -> logger.info called with resume_token_savings event."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()
        session = _make_session(
            messages=[{"role": "user", "content": "prior history"}],
        )

        mock_logger = MagicMock()

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="A medium system prompt with enough text to estimate",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="Methodology block with detailed steps",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
            patch("app.runtime.prompt_builder.logger", mock_logger),
        ):
            await builder.build(agent, ctx, session=session)

        # Find the resume_token_savings log call
        info_calls = mock_logger.info.call_args_list
        savings_calls = [
            c for c in info_calls
            if c[0][0] == "prompt_builder.resume_token_savings"
        ]
        assert len(savings_calls) == 1
        kwargs = savings_calls[0][1]
        assert kwargs["is_resume"] is True
        assert kwargs["saved_tokens"] > 0

    async def test_fresh_session_no_savings_logged(self) -> None:
        """Fresh session -> no resume_token_savings log emitted."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()

        mock_logger = MagicMock()

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="L1",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="L2",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
            patch("app.runtime.prompt_builder.logger", mock_logger),
        ):
            await builder.build(agent, ctx, session=None)

        info_calls = mock_logger.info.call_args_list
        savings_calls = [
            c for c in info_calls
            if c[0][0] == "prompt_builder.resume_token_savings"
        ]
        assert len(savings_calls) == 0

    async def test_resume_existing_messages_returned_as_is(self) -> None:
        """Resume session with full message history returns those messages directly."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()

        existing = [
            {"role": "user", "content": "Investigate alert 42"},
            {"role": "assistant", "content": "I found suspicious activity..."},
        ]
        session = _make_session(messages=existing)

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="L1",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="L2",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value="LAYER4",
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
        ):
            result = await builder.build(agent, ctx, session=session)

        # Messages should be the existing session messages (layer 5)
        assert result.messages == existing

    async def test_session_total_tokens_includes_existing_messages(self) -> None:
        """Resume session -> total_tokens_estimated includes tokens from existing messages."""
        builder = _make_builder()
        agent = _make_agent()
        ctx = _make_context()

        long_content = "x" * 400  # 100 tokens
        session = _make_session(
            messages=[{"role": "user", "content": long_content}],
        )

        with (
            patch.object(
                builder, "_build_layer1", new_callable=AsyncMock,
                return_value="L1",
            ),
            patch.object(
                builder, "_build_layer2",
                return_value="L2",
            ),
            patch.object(
                builder, "_build_layer3_kb", new_callable=AsyncMock,
                return_value=("", 0),
            ),
            patch.object(
                builder, "_build_layer4_alert_context", new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                builder, "_build_layer6_checkpoint", new_callable=AsyncMock,
                return_value="L6",
            ),
        ):
            result = await builder.build(agent, ctx, session=session)

        # Should account for existing message tokens (400 chars / 4 = 100)
        assert result.total_tokens_estimated >= 100
