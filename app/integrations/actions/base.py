"""ActionIntegration ABC and supporting types for the action execution engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """Result of an action execution attempt. Never raises — always returns."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    rollback_supported: bool = False

    @classmethod
    def ok(cls, message: str, data: dict[str, Any] | None = None) -> ExecutionResult:
        """Return a successful result."""
        return cls(success=True, message=message, data=data or {})

    @classmethod
    def fail(cls, message: str, data: dict[str, Any] | None = None) -> ExecutionResult:
        """Return a failure result."""
        return cls(success=False, message=message, data=data or {})


# ---------------------------------------------------------------------------
# Approval mode defaults per action_type
# ---------------------------------------------------------------------------

ACTION_TYPE_DEFAULT_APPROVAL_MODE: dict[str, str] = {
    "containment": "always",
    "remediation": "always",
    "notification": "never",
    "escalation": "never",
    "enrichment": "never",
    "investigation": "never",
    "user_validation": "never",
    "custom": "always",
}


# ---------------------------------------------------------------------------
# Confidence-based approval resolution
# ---------------------------------------------------------------------------


def resolve_approval_mode_for_action(
    action_type: str,
    confidence: float | None,
    base_approval_mode: str,
    bypass_confidence_override: bool = False,
) -> str:
    """
    Determine the effective approval mode for an action based on:
      1. ``base_approval_mode`` (from integration config or action_type default)
      2. confidence score (only applied when ``bypass_confidence_override`` is False)

    Confidence override table (from PRD):
      >= 0.95  → auto_approve
      >= 0.85  → quick_review
      >= 0.70  → human_review
      <  0.70  → block

    Returns one of: "auto_approve", "quick_review", "human_review", "block", "never".
    """
    if base_approval_mode == "never":
        return "never"

    if bypass_confidence_override or confidence is None:
        return base_approval_mode

    # Confidence override table
    if confidence >= 0.95:
        return "auto_approve"
    elif confidence >= 0.85:
        return "quick_review"
    elif confidence >= 0.70:
        return "human_review"
    else:
        return "block"


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class ActionIntegration(ABC):
    """
    Base class for action execution integrations.
    Same pattern as EnrichmentProviderBase — ports and adapters.

    Subclass this to add a new integration.
    See app/integrations/actions/CONTEXT.md for the full extension pattern.

    Contract:
      - ``execute()`` MUST NEVER raise. Catch all errors and return ExecutionResult.fail().
      - ``rollback()`` MUST NEVER raise. Default implementation returns unsupported.
      - ``is_configured()`` MUST NOT raise.
    """

    # Default approval mode for this integration's action types.
    # Override in subclass to change default.
    default_approval_mode: str = "always"

    # If True, confidence score override is disabled — action always follows
    # base_approval_mode regardless of the agent's confidence value.
    bypass_confidence_override: bool = False

    @abstractmethod
    async def execute(self, action: AgentAction) -> ExecutionResult:
        """Execute the approved action. Must never raise — catch all errors."""
        ...

    async def rollback(self, action: AgentAction) -> ExecutionResult:
        """
        Reverse the action if possible.
        Default implementation returns unsupported. Override in subclass when
        the action type has a meaningful inverse (e.g. lift_containment reverses isolate_host).
        """
        return ExecutionResult.fail(
            f"{self.__class__.__name__} does not support rollback",
            {"rollback_supported": False},
        )

    @abstractmethod
    def supported_actions(self) -> list[str]:
        """Return list of action_subtypes this integration handles."""
        ...

    def is_configured(self) -> bool:
        """Return True if this integration has the required credentials."""
        return True
