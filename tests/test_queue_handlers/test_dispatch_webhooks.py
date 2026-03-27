"""Unit tests for DispatchWebhooksHandler and DispatchSingleWebhookHandler.

Tests the agent webhook dispatch handlers with mocked dependencies:
- AlertRepository (get_by_id)
- get_matching_agents
- build_webhook_payload
- dispatch_to_agent
- ActivityEventService (write)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.queue.handlers.dispatch_webhooks import (
    DispatchSingleWebhookHandler,
    DispatchWebhooksHandler,
)
from app.queue.handlers.payloads import (
    DispatchAgentWebhooksPayload,
    DispatchSingleAgentWebhookPayload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(*, name: str = "agent-1") -> MagicMock:
    agent = MagicMock()
    agent.id = 1
    agent.name = name
    agent.uuid = uuid4()
    return agent


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> DispatchWebhooksHandler:
    return DispatchWebhooksHandler()


@pytest.fixture
def single_handler() -> DispatchSingleWebhookHandler:
    return DispatchSingleWebhookHandler()


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# DispatchWebhooksHandler — Happy path
# ---------------------------------------------------------------------------


class TestDispatchWebhooksHappyPath:
    @pytest.mark.asyncio
    async def test_dispatches_to_matching_agents(
        self,
        handler: DispatchWebhooksHandler,
        session: AsyncMock,
    ) -> None:
        """Alert found, matching agents found, webhooks dispatched."""
        payload = DispatchAgentWebhooksPayload(alert_id=42)

        mock_alert = MagicMock()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        agent_1 = _make_agent(name="agent-1")
        agent_2 = _make_agent(name="agent-2")

        webhook_payload = {"data": {"alert_uuid": "abc-123"}}
        dispatch_result = {"status": "delivered", "status_code": 200, "attempt_count": 1}

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.get_matching_agents",
                new_callable=AsyncMock,
                return_value=[agent_1, agent_2],
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
                return_value=webhook_payload,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.dispatch_to_agent",
                new_callable=AsyncMock,
                return_value=dispatch_result,
            ) as mock_dispatch,
            patch(
                "app.queue.handlers.dispatch_webhooks.ActivityEventService"
            ),
        ):
            await handler.execute(payload, session)

        # dispatch_to_agent should be called once per agent
        assert mock_dispatch.await_count == 2


# ---------------------------------------------------------------------------
# DispatchWebhooksHandler — Alert not found
# ---------------------------------------------------------------------------


class TestDispatchWebhooksAlertNotFound:
    @pytest.mark.asyncio
    async def test_returns_gracefully_when_alert_missing(
        self,
        handler: DispatchWebhooksHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns without raising when alert doesn't exist."""
        payload = DispatchAgentWebhooksPayload(alert_id=999)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.get_matching_agents",
                new_callable=AsyncMock,
            ) as mock_matching,
        ):
            await handler.execute(payload, session)

        # Should not have tried to find matching agents
        mock_matching.assert_not_awaited()


# ---------------------------------------------------------------------------
# DispatchWebhooksHandler — No matching agents
# ---------------------------------------------------------------------------


class TestDispatchWebhooksNoMatchingAgents:
    @pytest.mark.asyncio
    async def test_returns_gracefully_when_no_agents_match(
        self,
        handler: DispatchWebhooksHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns gracefully when no agents match the alert."""
        payload = DispatchAgentWebhooksPayload(alert_id=42)

        mock_alert = MagicMock()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.get_matching_agents",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
            ) as mock_build,
        ):
            await handler.execute(payload, session)

        # build_webhook_payload should NOT be called if no agents match
        mock_build.assert_not_awaited()


# ---------------------------------------------------------------------------
# DispatchWebhooksHandler — Per-agent failure isolation
# ---------------------------------------------------------------------------


class TestDispatchWebhooksFailureIsolation:
    @pytest.mark.asyncio
    async def test_one_agent_failure_does_not_block_others(
        self,
        handler: DispatchWebhooksHandler,
        session: AsyncMock,
    ) -> None:
        """If dispatch_to_agent raises for one agent, the other agents still get dispatched."""
        payload = DispatchAgentWebhooksPayload(alert_id=42)

        mock_alert = MagicMock()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_id = AsyncMock(return_value=mock_alert)

        agent_1 = _make_agent(name="failing-agent")
        agent_2 = _make_agent(name="succeeding-agent")

        webhook_payload = {"data": {"alert_uuid": "abc-123"}}
        ok_result = {"status": "delivered", "status_code": 200, "attempt_count": 1}

        # First call raises, second succeeds
        dispatch_side_effects = [
            RuntimeError("agent-1 connection refused"),
            ok_result,
        ]

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.get_matching_agents",
                new_callable=AsyncMock,
                return_value=[agent_1, agent_2],
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
                return_value=webhook_payload,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.dispatch_to_agent",
                new_callable=AsyncMock,
                side_effect=dispatch_side_effects,
            ) as mock_dispatch,
            patch(
                "app.queue.handlers.dispatch_webhooks.ActivityEventService"
            ),
        ):
            # Should not raise even though agent_1 failed
            await handler.execute(payload, session)

        # Both agents should have been attempted
        assert mock_dispatch.await_count == 2

        # Session rollback called for the failed agent
        session.rollback.assert_awaited()


# ---------------------------------------------------------------------------
# DispatchSingleWebhookHandler — Happy path
# ---------------------------------------------------------------------------


class TestDispatchSingleWebhookHappyPath:
    @pytest.mark.asyncio
    async def test_dispatches_to_specific_agent(
        self,
        single_handler: DispatchSingleWebhookHandler,
        session: AsyncMock,
    ) -> None:
        """Dispatches webhook to a specific agent by ID."""
        payload = DispatchSingleAgentWebhookPayload(alert_id=42, agent_id=7)

        agent = _make_agent(name="target-agent")
        webhook_payload = {"data": {"alert_uuid": "abc"}}
        dispatch_result = {"status": "delivered", "status_code": 200, "attempt_count": 1}

        # session.execute returns the agent
        session.execute.return_value = _scalar_result(agent)

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
                return_value=webhook_payload,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.dispatch_to_agent",
                new_callable=AsyncMock,
                return_value=dispatch_result,
            ) as mock_dispatch,
            patch(
                "app.queue.handlers.dispatch_webhooks.ActivityEventService"
            ),
        ):
            await single_handler.execute(payload, session)

        mock_dispatch.assert_awaited_once()


# ---------------------------------------------------------------------------
# DispatchSingleWebhookHandler — Agent not found
# ---------------------------------------------------------------------------


class TestDispatchSingleWebhookAgentNotFound:
    @pytest.mark.asyncio
    async def test_returns_gracefully_when_agent_missing(
        self,
        single_handler: DispatchSingleWebhookHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns without raising when agent doesn't exist."""
        payload = DispatchSingleAgentWebhookPayload(alert_id=42, agent_id=999)

        session.execute.return_value = _scalar_result(None)

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
            ) as mock_build,
        ):
            await single_handler.execute(payload, session)

        mock_build.assert_not_awaited()


# ---------------------------------------------------------------------------
# DispatchSingleWebhookHandler — Alert not found (no payload)
# ---------------------------------------------------------------------------


class TestDispatchSingleWebhookAlertNotFound:
    @pytest.mark.asyncio
    async def test_returns_gracefully_when_alert_payload_empty(
        self,
        single_handler: DispatchSingleWebhookHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns gracefully when build_webhook_payload returns falsy."""
        payload = DispatchSingleAgentWebhookPayload(alert_id=42, agent_id=7)

        agent = _make_agent()
        session.execute.return_value = _scalar_result(agent)

        with (
            patch(
                "app.queue.handlers.dispatch_webhooks.build_webhook_payload",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.queue.handlers.dispatch_webhooks.dispatch_to_agent",
                new_callable=AsyncMock,
            ) as mock_dispatch,
        ):
            await single_handler.execute(payload, session)

        mock_dispatch.assert_not_awaited()
