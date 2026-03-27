"""
Unit tests for the agent trigger evaluation engine (Chunk 5.2).

Tests use mocked AgentRepository.list_active() and MagicMock alert/agent objects.
No DB or network calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.queue.handlers.dispatch_webhooks import (
    _passes_jsonb_filter,
    _passes_severity_filter,
    _passes_source_filter,
    get_matching_agents,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alert(
    source_name: str = "sentinel",
    severity: str = "High",
) -> MagicMock:
    alert = MagicMock()
    alert.source_name = source_name
    alert.severity = severity
    alert.severity_id = 4
    alert.tags = []
    return alert


def _make_agent(
    trigger_on_sources: list[str] | None = None,
    trigger_on_severities: list[str] | None = None,
    trigger_filter: dict | None = None,
    is_active: bool = True,
) -> MagicMock:
    agent = MagicMock()
    agent.is_active = is_active
    agent.trigger_on_sources = trigger_on_sources or []
    agent.trigger_on_severities = trigger_on_severities or []
    agent.trigger_filter = trigger_filter
    return agent


# ---------------------------------------------------------------------------
# _passes_source_filter
# ---------------------------------------------------------------------------


def test_source_filter_empty_list_matches_any() -> None:
    agent = _make_agent(trigger_on_sources=[])
    alert = _make_alert(source_name="elastic")
    assert _passes_source_filter(agent, alert) is True


def test_source_filter_matches_when_source_in_list() -> None:
    agent = _make_agent(trigger_on_sources=["sentinel", "elastic"])
    alert = _make_alert(source_name="elastic")
    assert _passes_source_filter(agent, alert) is True


def test_source_filter_skips_when_source_not_in_list() -> None:
    agent = _make_agent(trigger_on_sources=["sentinel"])
    alert = _make_alert(source_name="splunk")
    assert _passes_source_filter(agent, alert) is False


def test_source_filter_is_case_sensitive() -> None:
    agent = _make_agent(trigger_on_sources=["Sentinel"])
    alert = _make_alert(source_name="sentinel")
    assert _passes_source_filter(agent, alert) is False


# ---------------------------------------------------------------------------
# _passes_severity_filter
# ---------------------------------------------------------------------------


def test_severity_filter_empty_list_matches_any() -> None:
    agent = _make_agent(trigger_on_severities=[])
    alert = _make_alert(severity="Low")
    assert _passes_severity_filter(agent, alert) is True


def test_severity_filter_matches_when_severity_in_list() -> None:
    agent = _make_agent(trigger_on_severities=["High", "Critical"])
    alert = _make_alert(severity="Critical")
    assert _passes_severity_filter(agent, alert) is True


def test_severity_filter_skips_when_severity_not_in_list() -> None:
    agent = _make_agent(trigger_on_severities=["High", "Critical"])
    alert = _make_alert(severity="Low")
    assert _passes_severity_filter(agent, alert) is False


def test_severity_filter_is_case_sensitive() -> None:
    agent = _make_agent(trigger_on_severities=["high"])
    alert = _make_alert(severity="High")
    assert _passes_severity_filter(agent, alert) is False


# ---------------------------------------------------------------------------
# _passes_jsonb_filter
# ---------------------------------------------------------------------------


def test_jsonb_filter_none_matches_all() -> None:
    agent = _make_agent(trigger_filter=None)
    alert = _make_alert()
    assert _passes_jsonb_filter(agent, alert) is True


def test_jsonb_filter_empty_dict_matches_all() -> None:
    agent = _make_agent(trigger_filter={})
    alert = _make_alert()
    assert _passes_jsonb_filter(agent, alert) is True


def test_jsonb_filter_match_any_passes_when_rule_matches() -> None:
    agent = _make_agent(
        trigger_filter={
            "match_any": [{"field": "source_name", "op": "eq", "value": "sentinel"}]
        }
    )
    alert = _make_alert(source_name="sentinel")
    assert _passes_jsonb_filter(agent, alert) is True


def test_jsonb_filter_match_any_fails_when_no_rule_matches() -> None:
    agent = _make_agent(
        trigger_filter={
            "match_any": [{"field": "source_name", "op": "eq", "value": "elastic"}]
        }
    )
    alert = _make_alert(source_name="splunk")
    assert _passes_jsonb_filter(agent, alert) is False


def test_jsonb_filter_match_all_passes_when_all_rules_match() -> None:
    agent = _make_agent(
        trigger_filter={
            "match_all": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
                {"field": "severity", "op": "eq", "value": "High"},
            ]
        }
    )
    alert = _make_alert(source_name="sentinel", severity="High")
    assert _passes_jsonb_filter(agent, alert) is True


def test_jsonb_filter_match_all_fails_when_any_rule_fails() -> None:
    agent = _make_agent(
        trigger_filter={
            "match_all": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
                {"field": "severity", "op": "eq", "value": "Critical"},
            ]
        }
    )
    alert = _make_alert(source_name="sentinel", severity="High")
    assert _passes_jsonb_filter(agent, alert) is False


# ---------------------------------------------------------------------------
# Combined filter tests (source + severity)
# ---------------------------------------------------------------------------


def test_combined_source_and_severity_both_must_pass() -> None:
    agent = _make_agent(
        trigger_on_sources=["sentinel"],
        trigger_on_severities=["High", "Critical"],
    )
    # Both match
    alert = _make_alert(source_name="sentinel", severity="High")
    assert _passes_source_filter(agent, alert) is True
    assert _passes_severity_filter(agent, alert) is True


def test_combined_source_passes_severity_fails() -> None:
    agent = _make_agent(
        trigger_on_sources=["sentinel"],
        trigger_on_severities=["High", "Critical"],
    )
    alert = _make_alert(source_name="sentinel", severity="Low")
    assert _passes_source_filter(agent, alert) is True
    assert _passes_severity_filter(agent, alert) is False


def test_combined_source_fails_severity_passes() -> None:
    agent = _make_agent(
        trigger_on_sources=["elastic"],
        trigger_on_severities=["High", "Critical"],
    )
    alert = _make_alert(source_name="sentinel", severity="High")
    assert _passes_source_filter(agent, alert) is False
    assert _passes_severity_filter(agent, alert) is True


# ---------------------------------------------------------------------------
# get_matching_agents — integration of all three passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_matching_agents_returns_agent_with_all_empty_filters() -> None:
    """Agent with empty lists and None filter matches any alert."""
    agent = _make_agent(
        trigger_on_sources=[],
        trigger_on_severities=[],
        trigger_filter=None,
    )
    alert = _make_alert(source_name="sentinel", severity="High")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == [agent]


@pytest.mark.asyncio
async def test_get_matching_agents_source_filter_excludes_non_matching() -> None:
    """Agent with source filter skips alert from different source."""
    agent = _make_agent(trigger_on_sources=["elastic"])
    alert = _make_alert(source_name="sentinel")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_get_matching_agents_source_filter_includes_matching() -> None:
    """Agent with source filter matches when alert.source_name is in the list."""
    agent = _make_agent(trigger_on_sources=["sentinel", "elastic"])
    alert = _make_alert(source_name="elastic")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == [agent]


@pytest.mark.asyncio
async def test_get_matching_agents_severity_filter_excludes_non_matching() -> None:
    """Agent with severity filter skips alert with different severity."""
    agent = _make_agent(trigger_on_severities=["Critical"])
    alert = _make_alert(severity="Low")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_get_matching_agents_severity_filter_includes_matching() -> None:
    """Agent with severity filter matches when alert.severity is in the list."""
    agent = _make_agent(trigger_on_severities=["High", "Critical"])
    alert = _make_alert(severity="Critical")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == [agent]


@pytest.mark.asyncio
async def test_get_matching_agents_jsonb_filter_excludes_non_matching() -> None:
    """Agent with JSONB filter skips alert that does not satisfy the rule."""
    agent = _make_agent(
        trigger_filter={
            "match_all": [{"field": "source_name", "op": "eq", "value": "elastic"}]
        }
    )
    alert = _make_alert(source_name="sentinel")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_get_matching_agents_jsonb_filter_includes_matching() -> None:
    """Agent with JSONB filter matches alert that satisfies the rule."""
    agent = _make_agent(
        trigger_filter={
            "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}]
        }
    )
    alert = _make_alert(severity="High")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result = await get_matching_agents(alert, mock_db)

    assert result == [agent]


@pytest.mark.asyncio
async def test_get_matching_agents_multiple_agents_partial_match() -> None:
    """Only agents whose all filters pass are returned from a mixed set."""
    matching_agent = _make_agent(
        trigger_on_sources=["sentinel"],
        trigger_on_severities=[],
        trigger_filter=None,
    )
    non_matching_source = _make_agent(
        trigger_on_sources=["elastic"],
        trigger_on_severities=[],
        trigger_filter=None,
    )
    non_matching_severity = _make_agent(
        trigger_on_sources=[],
        trigger_on_severities=["Low"],
        trigger_filter=None,
    )
    alert = _make_alert(source_name="sentinel", severity="High")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(
            return_value=[matching_agent, non_matching_source, non_matching_severity]
        )
        result = await get_matching_agents(alert, mock_db)

    assert result == [matching_agent]


@pytest.mark.asyncio
async def test_get_matching_agents_no_active_agents_returns_empty() -> None:
    """When list_active() returns empty, result is empty."""
    alert = _make_alert()
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[])
        result = await get_matching_agents(alert, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_get_matching_agents_all_filters_combined() -> None:
    """Source + severity + JSONB filter: all three must pass."""
    agent = _make_agent(
        trigger_on_sources=["sentinel"],
        trigger_on_severities=["High", "Critical"],
        trigger_filter={
            "match_all": [{"field": "severity", "op": "eq", "value": "High"}]
        },
    )
    # Alert that satisfies all three filters
    alert_match = _make_alert(source_name="sentinel", severity="High")
    # Alert that fails on severity list filter
    alert_no_match = _make_alert(source_name="sentinel", severity="Low")
    mock_db = MagicMock()

    with patch(
        "app.queue.handlers.dispatch_webhooks.AgentRepository"
    ) as MockRepo:
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])

        result_match = await get_matching_agents(alert_match, mock_db)
        MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
        result_no_match = await get_matching_agents(alert_no_match, mock_db)

    assert result_match == [agent]
    assert result_no_match == []
