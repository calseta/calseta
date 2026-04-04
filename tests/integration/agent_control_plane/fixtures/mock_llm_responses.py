"""Canned LLM response sequences for mocking LLMProviderAdapter.create_message."""

from __future__ import annotations

from app.integrations.llm.base import CostInfo, LLMResponse

# ---------------------------------------------------------------------------
# Simple text completion — no tool calls
# ---------------------------------------------------------------------------

SIMPLE_TEXT_RESPONSE = LLMResponse(
    content=[{"type": "text", "text": "Alert classified as false positive. Confidence: 0.92."}],
    stop_reason="end_turn",
    usage=CostInfo(input_tokens=1500, output_tokens=200, cost_cents=5, billing_type="api"),
)

# ---------------------------------------------------------------------------
# Tool call sequence — two-turn: tool_use → end_turn
# ---------------------------------------------------------------------------

TOOL_CALL_SEQUENCE = [
    # Turn 1: agent calls get_alert
    LLMResponse(
        content=[
            {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "get_alert",
                "input": {"alert_uuid": "test-uuid"},
            }
        ],
        stop_reason="tool_use",
        usage=CostInfo(input_tokens=2000, output_tokens=100, cost_cents=7, billing_type="api"),
    ),
    # Turn 2: agent processes result and responds
    LLMResponse(
        content=[
            {"type": "text", "text": "Investigation complete. True positive with high confidence."}
        ],
        stop_reason="end_turn",
        usage=CostInfo(input_tokens=3000, output_tokens=300, cost_cents=11, billing_type="api"),
    ),
]

# ---------------------------------------------------------------------------
# Budget exceeded mid-loop — large cost event
# ---------------------------------------------------------------------------

BUDGET_EXCEEDED_RESPONSE = LLMResponse(
    content=[{"type": "text", "text": "Partial analysis..."}],
    stop_reason="end_turn",
    usage=CostInfo(
        input_tokens=50000, output_tokens=5000, cost_cents=999999, billing_type="api"
    ),
)
