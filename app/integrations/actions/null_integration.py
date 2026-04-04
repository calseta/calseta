"""NullActionIntegration — no-op fallback when no real integration is configured."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()


class NullActionIntegration(ActionIntegration):
    """
    No-op integration used when no specific integration handles an action_subtype.

    Logs the action and returns success. Approval mode is "never" so these
    actions are not held up in the approval queue.
    """

    default_approval_mode = "never"
    bypass_confidence_override = False

    async def execute(self, action: AgentAction) -> ExecutionResult:
        logger.info(
            "null_action_integration_executed",
            action_id=str(action.uuid),
            action_type=action.action_type,
            action_subtype=action.action_subtype,
        )
        return ExecutionResult.ok(
            f"[null] Action {action.action_subtype} acknowledged (no integration configured)",
            {"action_id": str(action.uuid), "action_type": action.action_type},
        )

    def supported_actions(self) -> list[str]:
        # "*" signals the registry that this catches anything not explicitly registered.
        return ["*"]
