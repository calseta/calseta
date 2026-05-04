"""Pydantic input models for write-tier agent tools (S2 — Tool Output Validation Gate).

Every write-side built-in tool exposed via the agent runtime MUST register an
input model here. The dispatcher validates ``tool_input`` against the registered
model before invoking the handler. Validation failure is surfaced to the LLM as
a coarse error code — never the raw exception string.

Why: prior to S2 the LLM controlled raw dicts that flowed straight into the
repositories (e.g. arbitrary ``classification`` strings, oversized
``reasoning`` payloads, ``alert_uuid`` overrides). This module is the single
boundary where untrusted tool inputs become validated, typed objects.

Read-tier tools (e.g. ``get_alert``, ``search_alerts``) are intentionally
unregistered here — they pass raw dicts through to handlers that perform
their own narrow validation. Only write/managed-tier tools require strict
input modelling.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.alert import AlertStatus

# ---------------------------------------------------------------------------
# Canonical enum surface for write-tier tools
# ---------------------------------------------------------------------------

# Classification values accepted by ``post_finding``. Must match the JSON-Schema
# enum seeded for the tool in ``app/seed/builtin_tools.py``.
POST_FINDING_CLASSIFICATIONS: tuple[str, ...] = (
    "true_positive",
    "false_positive",
    "benign",
    "inconclusive",
)

# Maximum reasoning length the LLM may submit on a single finding.
MAX_REASONING_CHARS = 4000

# Maximum number of structured findings entries inside a single post_finding call.
MAX_FINDINGS_ITEMS = 50


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class _StrictToolInput(BaseModel):
    """Base for all tool input models — extras forbidden, no implicit coercion."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class PostFindingInput(_StrictToolInput):
    """Validated input for ``calseta:post_finding``.

    The ``alert_uuid`` field is required because the LLM addresses findings by
    UUID; the dispatcher cross-checks it against the active investigation
    context (``RuntimeContext.alert_id``) before mutating the alert. Mismatched
    UUIDs short-circuit to ``alert_scope_violation`` without touching the DB.
    """

    alert_uuid: UUID
    classification: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=MAX_REASONING_CHARS)
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_FINDINGS_ITEMS)

    @field_validator("classification")
    @classmethod
    def _classification_in_enum(cls, value: str) -> str:
        if value not in POST_FINDING_CLASSIFICATIONS:
            allowed = ", ".join(POST_FINDING_CLASSIFICATIONS)
            raise ValueError(
                f"classification must be one of: {allowed}",
            )
        return value


class UpdateAlertStatusInput(_StrictToolInput):
    """Validated input for ``calseta:update_alert_status``.

    ``alert_uuid`` is accepted (the LLM still passes it for self-consistency)
    but the dispatcher IGNORES it for the actual mutation — the target alert is
    always ``RuntimeContext.alert_id``. A mismatched UUID is a scope violation.
    """

    alert_uuid: UUID
    status: AlertStatus
    reason: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Registry — operation name (handler_ref suffix) → input model
# ---------------------------------------------------------------------------

ToolInputModel = type[_StrictToolInput]

TOOL_INPUT_MODELS: dict[str, ToolInputModel] = {
    "post_finding": PostFindingInput,
    "update_alert_status": UpdateAlertStatusInput,
}


__all__ = [
    "MAX_FINDINGS_ITEMS",
    "MAX_REASONING_CHARS",
    "POST_FINDING_CLASSIFICATIONS",
    "TOOL_INPUT_MODELS",
    "PostFindingInput",
    "ToolInputModel",
    "UpdateAlertStatusInput",
]
