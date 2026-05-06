"""S15 — agent_findings canonical schema.

Verifies that ``_handle_post_finding`` writes the canonical FindingResponse
shape and that ``GET /v1/alerts/{uuid}/findings`` reads it back without any
shape coercion.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.integrations.tools.dispatcher import (
    _confidence_numeric_to_enum,
    _handle_post_finding,
)
from app.schemas.alerts import FindingResponse
from app.schemas.tool_inputs import PostFindingInput
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import (
    create_enriched_alert,
)
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Pure-unit confidence mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.97, "high"),
        (0.75, "high"),
        (0.5, "medium"),
        (0.4, "medium"),
        (0.39, "low"),
        (0.0, "low"),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_confidence_numeric_to_enum(raw: Any, expected: str | None) -> None:
    assert _confidence_numeric_to_enum(raw) == expected


# ---------------------------------------------------------------------------
# Handler writes canonical shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_post_finding_writes_canonical_shape(
    db_session: AsyncSession,
) -> None:
    agent, _ = await _create_agent_with_key(db_session, name="canonical-test-agent")
    alert: Alert = await create_enriched_alert(db_session)

    tool_input = PostFindingInput.model_validate(
        {
            "alert_uuid": str(alert.uuid),
            "classification": "true_positive",
            "confidence": 0.97,
            "reasoning": "Saw lateral movement followed by credential dump.",
            "findings": [{"type": "lateral_movement"}],
        },
    )
    result = await _handle_post_finding(db_session, agent, tool_input, None)

    assert result["status"] == "ok", result
    assert result["data"]["confidence"] == "high"
    assert result["data"]["recorded"] is True

    # Round-trip through the canonical response schema
    await db_session.refresh(alert)
    findings = alert.agent_findings or []
    assert len(findings) == 1
    persisted = findings[0]

    parsed = FindingResponse.model_validate(persisted)
    assert parsed.agent_name == "canonical-test-agent"
    assert parsed.summary == "Saw lateral movement followed by credential dump."
    assert parsed.confidence is not None
    assert parsed.confidence.value == "high"
    assert parsed.recommended_action is None

    # Raw confidence + classification + extra findings preserved under evidence
    assert parsed.evidence is not None
    assert parsed.evidence["confidence_raw"] == 0.97
    assert parsed.evidence["classification"] == "true_positive"
    assert parsed.evidence["findings"] == [{"type": "lateral_movement"}]
    # Original reasoning equals summary → not duplicated under evidence.reasoning
    assert "reasoning" not in parsed.evidence
    assert parsed.evidence["agent_id"] == agent.id


@pytest.mark.asyncio
async def test_handle_post_finding_low_confidence_bucket(
    db_session: AsyncSession,
) -> None:
    agent, _ = await _create_agent_with_key(db_session, name="low-conf-agent")
    alert: Alert = await create_enriched_alert(db_session)

    tool_input = PostFindingInput.model_validate(
        {
            "alert_uuid": str(alert.uuid),
            "classification": "inconclusive",
            "confidence": 0.1,
            "reasoning": "Insufficient signal.",
        },
    )
    result = await _handle_post_finding(db_session, agent, tool_input, None)

    assert result["status"] == "ok"
    assert result["data"]["confidence"] == "low"

    await db_session.refresh(alert)
    persisted = (alert.agent_findings or [])[0]
    assert FindingResponse.model_validate(persisted).confidence is not None
    assert persisted["confidence"] == "low"
    assert persisted["evidence"]["confidence_raw"] == 0.1


# ---------------------------------------------------------------------------
# GET /v1/alerts/{uuid}/findings returns the persisted canonical row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_findings_returns_canonical_after_dispatch(
    db_session: AsyncSession,
    test_client: AsyncClient,
    api_key: str,
) -> None:
    agent, _ = await _create_agent_with_key(db_session, name="api-readback-agent")
    alert: Alert = await create_enriched_alert(db_session)

    tool_input = PostFindingInput.model_validate(
        {
            "alert_uuid": str(alert.uuid),
            "classification": "false_positive",
            "confidence": 0.62,
            "reasoning": "Known scanner traffic from approved partner.",
        },
    )
    handler_result = await _handle_post_finding(
        db_session, agent, tool_input, None,
    )
    assert handler_result["status"] == "ok"

    resp = await test_client.get(
        f"/v1/alerts/{alert.uuid}/findings",
        headers=auth_header(api_key),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["data"]
    assert len(items) == 1
    item = items[0]
    assert item["agent_name"] == "api-readback-agent"
    assert item["summary"] == "Known scanner traffic from approved partner."
    assert item["confidence"] == "medium"
    assert item["evidence"]["confidence_raw"] == 0.62
    assert item["evidence"]["classification"] == "false_positive"


# ---------------------------------------------------------------------------
# Defensive cases
# ---------------------------------------------------------------------------


def test_post_finding_input_rejects_invalid_uuid() -> None:
    """S2 catches invalid alert_uuid at the schema layer; handler never runs."""
    with pytest.raises(ValidationError):
        PostFindingInput.model_validate(
            {
                "alert_uuid": "not-a-uuid",
                "classification": "benign",
                "confidence": 0.5,
                "reasoning": "x",
            },
        )


def test_post_finding_input_rejects_empty_reasoning() -> None:
    """S2 enforces non-empty reasoning at the schema layer (str_strip_whitespace
    + min_length=1); the handler's "no reasoning provided" fallback is now
    unreachable from the dispatcher path."""
    with pytest.raises(ValidationError):
        PostFindingInput.model_validate(
            {
                "alert_uuid": "11111111-1111-1111-1111-111111111111",
                "classification": "benign",
                "confidence": 0.8,
                "reasoning": "   ",
            },
        )
