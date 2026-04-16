"""ToolDispatcher — routes managed agent tool calls to the correct handler.

Architecture:
  - Looks up tool by id from DB
  - Enforces tier permissions (forbidden → error, requires_approval → error)
  - Dispatches safe/managed tools to handler_ref implementations
  - handler_ref format: "calseta:<operation>" for built-in tools

Built-in handler stubs return structured results. Full service wiring happens
when AgentRuntimeEngine is implemented in a subsequent chunk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.agent_tool import AgentTool

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolForbiddenError(Exception):
    """Raised when a tool has tier='forbidden'."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' is forbidden for this agent.")


class ToolRequiresApprovalError(Exception):
    """Raised when a tool has tier='requires_approval' and no pre-approved context."""

    def __init__(self, tool_id: str, tool: AgentTool) -> None:
        self.tool_id = tool_id
        self.tool = tool
        super().__init__(
            f"Tool '{tool_id}' requires human approval before execution."
        )


class ToolNotFoundError(Exception):
    """Raised when the requested tool does not exist in the registry."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' not found in registry.")


class ToolNotAssignedError(Exception):
    """Raised when the agent attempts to call a tool not in its tool_ids list."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(
            f"Tool '{tool_id}' is not assigned to this agent. "
            "Update agent.tool_ids to grant access."
        )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class ToolDispatcher:
    """Routes managed agent tool calls to the correct handler.

    Enforces tier permissions and agent tool assignment before dispatch.
    Services are injected via constructor — no global singletons.
    """

    def __init__(
        self,
        db: AsyncSession,
        agent: AgentRegistration,
    ) -> None:
        self._db = db
        self._agent = agent

    async def dispatch(
        self,
        tool_id: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call.

        Steps:
          1. Look up tool by id in the registry
          2. Verify the tool is in agent.tool_ids
          3. Enforce tier: forbidden → ToolForbiddenError
          4. Enforce tier: requires_approval → ToolRequiresApprovalError
          5. Execute via handler_ref for safe/managed tools
          6. Return result dict

        Raises:
          ToolNotFoundError       — tool does not exist
          ToolNotAssignedError    — agent does not have this tool
          ToolForbiddenError      — tier is 'forbidden'
          ToolRequiresApprovalError — tier is 'requires_approval'
        """
        from app.repositories.agent_tool_repository import AgentToolRepository

        repo = AgentToolRepository(self._db)
        tool = await repo.get_by_id(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)

        # Check agent is assigned this tool
        agent_tool_ids: list[str] = self._agent.tool_ids or []
        if tool_id not in agent_tool_ids:
            raise ToolNotAssignedError(tool_id)

        if not tool.is_active:
            raise ToolForbiddenError(tool_id)

        if tool.tier == "forbidden":
            raise ToolForbiddenError(tool_id)

        if tool.tier == "requires_approval":
            raise ToolRequiresApprovalError(tool_id, tool)

        # tier in ('safe', 'managed') — execute
        logger.info(
            "tool_dispatch",
            tool_id=tool_id,
            tier=tool.tier,
            handler_ref=tool.handler_ref,
            agent_id=self._agent.id,
        )
        return await self._execute_handler(tool, tool_input)

    async def _execute_handler(
        self,
        tool: AgentTool,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Route to the correct handler implementation based on handler_ref.

        Built-in handler_refs follow the pattern "calseta:<operation>".
        Each handler calls into the appropriate service layer.
        """
        handler_ref = tool.handler_ref

        if not handler_ref.startswith("calseta:"):
            logger.warning(
                "unknown_handler_ref",
                handler_ref=handler_ref,
                tool_id=tool.id,
            )
            return {
                "status": "error",
                "error": f"Unknown handler_ref: {handler_ref}",
            }

        operation = handler_ref.removeprefix("calseta:")
        handler = _BUILTIN_HANDLERS.get(operation)
        if handler is None:
            logger.warning(
                "unimplemented_builtin_handler",
                operation=operation,
                tool_id=tool.id,
            )
            return {
                "status": "error",
                "error": f"Built-in handler '{operation}' is not implemented.",
            }

        return await handler(self._db, self._agent, tool_input)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Built-in handler implementations
# ---------------------------------------------------------------------------
# Each handler receives (db, agent, tool_input) and returns a dict.
# Full service wiring is implemented in subsequent chunks (AgentRuntimeEngine).
# These stubs return structured responses using real repositories where easy,
# falling back to {"status": "ok", "data": {}} placeholders for complex ops.

async def _handle_get_alert(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.alert_repository import AlertRepository

    alert_uuid_str = tool_input.get("alert_uuid", "")
    try:
        alert_uuid = UUID(str(alert_uuid_str))
    except ValueError:
        return {"status": "error", "error": "Invalid alert_uuid format."}

    repo = AlertRepository(db)
    alert = await repo.get_by_uuid(alert_uuid)
    if alert is None:
        return {"status": "error", "error": f"Alert {alert_uuid} not found."}

    return {
        "status": "ok",
        "data": {
            "uuid": str(alert.uuid),
            "title": alert.title,
            "severity": alert.severity,
            "status": alert.status,
            "source_name": alert.source_name,
            "description": alert.description,
            "occurred_at": alert.occurred_at.isoformat() if alert.occurred_at else None,
            "enrichment_status": alert.enrichment_status,
            "is_enriched": alert.is_enriched,
            "tags": alert.tags,
        },
    }


async def _handle_search_alerts(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.alert_repository import AlertRepository

    repo = AlertRepository(db)
    limit = int(tool_input.get("limit", 20))
    limit = min(limit, 100)

    alerts, total = await repo.list_alerts(
        status=tool_input.get("status"),
        severity=tool_input.get("severity"),
        page=1,
        page_size=limit,
    )
    return {
        "status": "ok",
        "data": {
            "total": total,
            "alerts": [
                {
                    "uuid": str(a.uuid),
                    "title": a.title,
                    "severity": a.severity,
                    "status": a.status,
                    "source_name": a.source_name,
                    "occurred_at": a.occurred_at.isoformat() if a.occurred_at else None,
                    "is_enriched": a.is_enriched,
                }
                for a in alerts
            ],
        },
    }


async def _handle_get_enrichment(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.indicator_repository import IndicatorRepository

    indicator_type = tool_input.get("indicator_type", "")
    value = tool_input.get("value", "")
    if not indicator_type or not value:
        return {"status": "error", "error": "indicator_type and value are required."}

    repo = IndicatorRepository(db)
    indicator = await repo.get_by_type_and_value(indicator_type, str(value))
    if indicator is None:
        return {
            "status": "ok",
            "data": {
                "indicator_type": indicator_type,
                "value": value,
                "found": False,
                "enrichment_results": {},
            },
        }

    return {
        "status": "ok",
        "data": {
            "indicator_type": indicator.type,
            "value": indicator.value,
            "found": True,
            "malice": indicator.malice,
            "first_seen": indicator.first_seen.isoformat() if indicator.first_seen else None,
            "last_seen": indicator.last_seen.isoformat() if indicator.last_seen else None,
            "enrichment_results": indicator.enrichment_results or {},
        },
    }


async def _handle_post_finding(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.alert_repository import AlertRepository

    alert_uuid_str = tool_input.get("alert_uuid", "")
    try:
        alert_uuid = UUID(str(alert_uuid_str))
    except ValueError:
        return {"status": "error", "error": "Invalid alert_uuid format."}

    repo = AlertRepository(db)
    alert = await repo.get_by_uuid(alert_uuid)
    if alert is None:
        return {"status": "error", "error": f"Alert {alert_uuid} not found."}

    from datetime import UTC, datetime

    finding = {
        "classification": tool_input.get("classification"),
        "confidence": tool_input.get("confidence"),
        "reasoning": tool_input.get("reasoning"),
        "findings": tool_input.get("findings", []),
        "recorded_at": datetime.now(UTC).isoformat(),
        "agent_id": agent.id,
    }
    await repo.add_finding(alert, finding)
    await db.flush()

    return {
        "status": "ok",
        "data": {
            "alert_uuid": str(alert.uuid),
            "classification": finding["classification"],
            "confidence": finding["confidence"],
            "recorded": True,
        },
    }


async def _handle_update_alert_status(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.alert_repository import AlertRepository
    from app.schemas.alert import AlertStatus

    alert_uuid_str = tool_input.get("alert_uuid", "")
    new_status_str = tool_input.get("status", "")
    try:
        alert_uuid = UUID(str(alert_uuid_str))
    except ValueError:
        return {"status": "error", "error": "Invalid alert_uuid format."}

    try:
        new_status = AlertStatus(new_status_str)
    except ValueError:
        return {"status": "error", "error": f"Invalid status value: '{new_status_str}'."}

    repo = AlertRepository(db)
    alert = await repo.get_by_uuid(alert_uuid)
    if alert is None:
        return {"status": "error", "error": f"Alert {alert_uuid} not found."}

    updated = await repo.patch(alert, status=new_status)
    await db.flush()

    return {
        "status": "ok",
        "data": {
            "alert_uuid": str(updated.uuid),
            "status": updated.status,
        },
    }


async def _handle_get_detection_rule(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.detection_rule_repository import DetectionRuleRepository

    rule_uuid_str = tool_input.get("rule_uuid", "")
    try:
        rule_uuid = UUID(str(rule_uuid_str))
    except ValueError:
        return {"status": "error", "error": "Invalid rule_uuid format."}

    repo = DetectionRuleRepository(db)
    rule = await repo.get_by_uuid(rule_uuid)
    if rule is None:
        return {"status": "error", "error": f"Detection rule {rule_uuid} not found."}

    return {
        "status": "ok",
        "data": {
            "uuid": str(rule.uuid),
            "name": rule.name,
            "documentation": rule.documentation,
            "mitre_tactics": rule.mitre_tactics,
            "mitre_techniques": rule.mitre_techniques,
            "mitre_subtechniques": rule.mitre_subtechniques,
            "data_sources": rule.data_sources,
            "severity": rule.severity,
        },
    }



async def _handle_execute_workflow(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    # execute_workflow has tier=requires_approval, so this handler is never reached
    # via normal dispatch (ToolRequiresApprovalError is raised first).
    # Included for completeness if approval gating is bypassed in future.
    return {
        "status": "ok",
        "data": {},
    }


# Registry mapping operation name → handler function
_BUILTIN_HANDLERS: dict[
    str,
    Any,
] = {
    "get_alert": _handle_get_alert,
    "search_alerts": _handle_search_alerts,
    "get_enrichment": _handle_get_enrichment,
    "post_finding": _handle_post_finding,
    "update_alert_status": _handle_update_alert_status,
    "get_detection_rule": _handle_get_detection_rule,
    "execute_workflow": _handle_execute_workflow,
}
