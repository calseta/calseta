"""MCP tools for agent action operations — Phase 2 agent control plane.

Tools (write/execute):
  - propose_action       — Propose an action for an alert
  - get_action_status    — Get current status of an action
  - complete_assignment  — Mark an assignment as resolved
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def propose_action(
    alert_uuid: str,
    assignment_uuid: str,
    action_type: str,
    action_subtype: str,
    payload: dict[str, Any],
    ctx: Context,
    confidence: float | None = None,
    reasoning: str | None = None,
) -> str:
    """Propose an action for a security alert.

    The action is evaluated for approval requirements based on action_type and confidence.
    High-confidence actions for low-risk types may be auto-executed. Others require human approval.

    Args:
        alert_uuid: UUID of the alert the action is for.
        assignment_uuid: UUID of the agent's assignment for this alert.
        action_type: Category of action. Valid values: "containment", "remediation",
                     "notification", "escalation", "enrichment", "investigation",
                     "user_validation", "custom".
        action_subtype: Specific action to perform (e.g. "block_ip", "disable_user",
                        "send_slack_notification", "isolate_host").
        payload: Action-specific parameters (e.g. {"ip": "1.2.3.4"} for block_ip).
        confidence: Agent confidence in this action (0.0–1.0). Higher confidence may
                    reduce approval requirements.
        reasoning: Human-readable explanation of why this action is being proposed.

    Returns:
        JSON with action_id, status, and optional approval_request_uuid and expires_at.
    """
    try:
        parsed_alert_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid alert UUID: {alert_uuid}"})

    try:
        parsed_assignment_uuid = _uuid.UUID(assignment_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid assignment UUID: {assignment_uuid}"})

    valid_action_types = {
        "containment", "remediation", "notification", "escalation",
        "enrichment", "investigation", "user_validation", "custom",
    }
    if action_type not in valid_action_types:
        return json.dumps({
            "error": (
                f"Invalid action_type '{action_type}'. "
                f"Must be one of: {sorted(valid_action_types)}"
            )
        })

    if confidence is not None and not (0.0 <= confidence <= 1.0):
        return json.dumps({"error": "confidence must be between 0.0 and 1.0"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from sqlalchemy import select

        from app.db.models.agent_registration import AgentRegistration
        from app.db.models.alert import Alert
        from app.db.models.alert_assignment import AlertAssignment

        # Resolve alert
        alert_result = await session.execute(
            select(Alert).where(Alert.uuid == parsed_alert_uuid)
        )
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            return json.dumps({"error": f"Alert not found: {alert_uuid}"})

        # Resolve assignment
        assignment_result = await session.execute(
            select(AlertAssignment).where(AlertAssignment.uuid == parsed_assignment_uuid)
        )
        assignment = assignment_result.scalar_one_or_none()
        if assignment is None:
            return json.dumps({"error": f"Assignment not found: {assignment_uuid}"})

        # For MCP we need an agent — resolve from MCP client or use a system agent
        # MCP tools operate in a trust context; look up a registered agent if possible
        client_id = _resolve_client_id(ctx)

        # Find agent by key prefix if possible (MCP context)
        agent_result = await session.execute(
            select(AgentRegistration).limit(1)  # best-effort for MCP context
        )
        agent = agent_result.scalar_one_or_none()
        if agent is None:
            return json.dumps({"error": "No agent registrations found. Register an agent first."})

        from app.schemas.actions import ActionType, ProposeActionRequest
        from app.services.action_service import ActionService

        try:
            action_type_enum = ActionType(action_type)
        except ValueError:
            return json.dumps({"error": f"Invalid action_type: {action_type}"})

        request = ProposeActionRequest(
            alert_id=parsed_alert_uuid,
            assignment_id=parsed_assignment_uuid,
            action_type=action_type_enum,
            action_subtype=action_subtype,
            payload=payload,
            confidence=confidence,
            reasoning=reasoning,
        )

        svc = ActionService(session)
        try:
            result = await svc.propose_action(
                agent=agent,
                request=request,
                actor_key_prefix=client_id,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        await session.commit()

        return json.dumps(
            {
                "action_id": str(result.action_id),
                "status": result.status,
                "approval_request_uuid": str(result.approval_request_uuid)
                if result.approval_request_uuid
                else None,
                "expires_at": result.expires_at.isoformat() if result.expires_at else None,
            },
            default=_json_serial,
        )


@mcp_server.tool()
async def get_action_status(
    action_uuid: str,
    ctx: Context,
) -> str:
    """Get the current status and details of an agent action.

    Args:
        action_uuid: UUID of the action to retrieve.

    Returns:
        JSON with full action details including status, execution_result, and timestamps.
    """
    try:
        parsed_uuid = _uuid.UUID(action_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {action_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        from app.repositories.agent_action_repository import AgentActionRepository

        repo = AgentActionRepository(session)
        action = await repo.get_by_uuid(parsed_uuid)
        if action is None:
            return json.dumps({"error": f"Action not found: {action_uuid}"})

        return json.dumps(
            {
                "uuid": str(action.uuid),
                "alert_id": action.alert_id,
                "agent_registration_id": action.agent_registration_id,
                "assignment_id": action.assignment_id,
                "action_type": action.action_type,
                "action_subtype": action.action_subtype,
                "status": action.status,
                "payload": action.payload,
                "confidence": float(action.confidence) if action.confidence is not None else None,
                "approval_request_id": action.approval_request_id,
                "execution_result": action.execution_result,
                "executed_at": action.executed_at.isoformat() if action.executed_at else None,
                "created_at": action.created_at.isoformat(),
                "updated_at": action.updated_at.isoformat(),
            },
            default=_json_serial,
        )


@mcp_server.tool()
async def complete_assignment(
    assignment_uuid: str,
    resolution_type: str,
    resolution: str,
    ctx: Context,
) -> str:
    """Mark an alert assignment as resolved.

    Call this when investigation is complete to release the alert back with findings.

    Args:
        assignment_uuid: UUID of the assignment to complete.
        resolution_type: Classification of the investigation result. Valid values:
                         "true_positive", "false_positive", "benign", "inconclusive".
        resolution: Human-readable summary of the investigation findings and
                    rationale for the resolution.

    Returns:
        JSON with the updated assignment UUID, status, resolution_type, and completed_at.
    """
    try:
        parsed_uuid = _uuid.UUID(assignment_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {assignment_uuid}"})

    valid_resolution_types = {"true_positive", "false_positive", "benign", "inconclusive"}
    if resolution_type not in valid_resolution_types:
        return json.dumps({
            "error": f"Invalid resolution_type '{resolution_type}'. "
                     f"Must be one of: {sorted(valid_resolution_types)}"
        })

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from sqlalchemy import select

        from app.db.models.alert_assignment import AlertAssignment

        result = await session.execute(
            select(AlertAssignment).where(AlertAssignment.uuid == parsed_uuid)
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            return json.dumps({"error": f"Assignment not found: {assignment_uuid}"})

        if assignment.status == "resolved":
            return json.dumps({"error": "Assignment is already resolved."})

        now = datetime.now(UTC)
        assignment.status = "resolved"
        assignment.resolution = resolution
        assignment.resolution_type = resolution_type
        assignment.completed_at = now
        await session.flush()

        client_id = _resolve_client_id(ctx)
        activity_svc = ActivityEventService(session)
        await activity_svc.write(
            ActivityEventType.ALERT_STATUS_UPDATED,
            actor_type="mcp",
            actor_key_prefix=client_id,
            alert_id=assignment.alert_id,
            references={
                "assignment_uuid": assignment_uuid,
                "from_status": "in_progress",
                "to_status": "resolved",
                "resolution_type": resolution_type,
            },
        )

        await session.commit()

        return json.dumps(
            {
                "assignment_uuid": assignment_uuid,
                "status": "resolved",
                "resolution_type": resolution_type,
                "completed_at": now.isoformat(),
            },
            default=_json_serial,
        )
