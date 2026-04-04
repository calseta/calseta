"""MCP tools for multi-agent orchestration — Phase 5.

Tools (orchestrators only):
  - list_available_agents   — Catalog of active specialists with capabilities
  - delegate_task           — Invoke a single specialist agent
  - delegate_parallel       — Invoke multiple specialists simultaneously
  - get_task_result         — Poll until an invocation completes
  - get_all_results         — All invocation results for the current alert

All tools enforce agent_type == 'orchestrator'. Specialists receive HTTP 403
if they attempt to call these tools.
"""

from __future__ import annotations

import asyncio
import json
import uuid as _uuid
from datetime import datetime
from typing import Any

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server

logger = structlog.get_logger(__name__)

# Long-poll settings for get_task_result
_POLL_INTERVAL_SECONDS = 0.5
_MAX_WAIT_SECONDS = 30


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def _resolve_orchestrator(  # type: ignore[return]
    ctx: Context,
    session: Any,
) -> tuple[Any, str | None]:
    """Resolve orchestrator agent from MCP context. Returns (agent, error_json)."""
    from sqlalchemy import select

    from app.db.models.agent_registration import AgentRegistration

    # Find active orchestrator agents — for MCP context use first available orchestrator
    result = await session.execute(
        select(AgentRegistration).where(
            AgentRegistration.agent_type == "orchestrator",
            AgentRegistration.status == "active",
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        return None, json.dumps({
            "error": "No active orchestrator agent found. Register an orchestrator first.",
            "code": "NOT_ORCHESTRATOR",
        })
    return agent, None


@mcp_server.tool()
async def list_available_agents(ctx: Context) -> str:
    """List all active specialist agents available for delegation.

    Returns a catalog of specialists with their capabilities, roles,
    and agent types. Use this before planning delegation to understand
    which specialists are available and what they can do.

    Returns:
        JSON array of specialist agent summaries with uuid, name, role,
        agent_type, status, capabilities, and description.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        orchestrator, err = await _resolve_orchestrator(ctx, session)
        if err:
            return err

        from app.services.invocation_service import InvocationService

        svc = InvocationService(session)
        catalog = await svc.get_catalog()

        return json.dumps(
            [
                {
                    "uuid": str(entry.uuid),
                    "name": entry.name,
                    "role": entry.role,
                    "agent_type": entry.agent_type,
                    "status": entry.status,
                    "capabilities": entry.capabilities,
                    "description": entry.description,
                }
                for entry in catalog
            ],
            default=_json_serial,
        )


@mcp_server.tool()
async def delegate_task(
    alert_uuid: str,
    child_agent_uuid: str,
    task_description: str,
    ctx: Context,
    input_context: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    timeout_seconds: int = 300,
    assignment_uuid: str | None = None,
) -> str:
    """Delegate a task to a specialist agent.

    Orchestrators use this to hand off focused sub-tasks to specialists.
    The invocation is queued and the specialist is executed asynchronously.
    Use get_task_result() to wait for completion.

    Args:
        alert_uuid: UUID of the alert being investigated.
        child_agent_uuid: UUID of the specialist to delegate to.
        task_description: Clear description of what the specialist should do.
        input_context: Structured data to pass to the specialist as context.
        output_schema: Expected structure of the specialist's result.
        timeout_seconds: Maximum time to wait for specialist (default: 300s).
        assignment_uuid: Optional UUID of the orchestrator's alert assignment.

    Returns:
        JSON with invocation_id, status, and child_agent_id.
    """
    try:
        parsed_alert_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid alert UUID: {alert_uuid}"})

    try:
        parsed_child_uuid = _uuid.UUID(child_agent_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid child_agent UUID: {child_agent_uuid}"})

    parsed_assignment_uuid = None
    if assignment_uuid is not None:
        try:
            parsed_assignment_uuid = _uuid.UUID(assignment_uuid)
        except ValueError:
            return json.dumps({"error": f"Invalid assignment UUID: {assignment_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        orchestrator, err = await _resolve_orchestrator(ctx, session)
        if err:
            return err

        from app.schemas.agent_invocations import DelegateTaskRequest
        from app.services.invocation_service import InvocationService

        request = DelegateTaskRequest(
            alert_id=parsed_alert_uuid,
            child_agent_id=parsed_child_uuid,
            task_description=task_description,
            input_context=input_context,
            output_schema=output_schema,
            timeout_seconds=timeout_seconds,
            assignment_id=parsed_assignment_uuid,
        )

        svc = InvocationService(session)
        client_id = _resolve_client_id(ctx)
        try:
            result = await svc.delegate_task(
                orchestrator=orchestrator,
                request=request,
                actor_key_prefix=client_id,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        await session.commit()

        return json.dumps(
            {
                "invocation_id": str(result.invocation_id),
                "status": result.status,
                "child_agent_id": str(result.child_agent_id) if result.child_agent_id else None,
            },
            default=_json_serial,
        )


@mcp_server.tool()
async def delegate_parallel(
    alert_uuid: str,
    tasks: list[dict[str, Any]],
    ctx: Context,
    assignment_uuid: str | None = None,
) -> str:
    """Delegate multiple tasks to specialists simultaneously (2–10 tasks).

    All tasks are enqueued atomically. Use get_task_result() or
    get_all_results() to wait for completion.

    Args:
        alert_uuid: UUID of the alert being investigated.
        tasks: List of 2–10 task objects, each with:
               - child_agent_id (str UUID of specialist)
               - task_description (str)
               - input_context (dict, optional)
               - output_schema (dict, optional)
               - timeout_seconds (int, default 300)
        assignment_uuid: Optional UUID of the orchestrator's alert assignment.

    Returns:
        JSON with list of invocation_id + status for each task.
    """
    try:
        parsed_alert_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid alert UUID: {alert_uuid}"})

    if not (2 <= len(tasks) <= 10):
        return json.dumps({"error": f"parallel delegation requires 2–10 tasks, got {len(tasks)}"})

    parsed_assignment_uuid = None
    if assignment_uuid is not None:
        try:
            parsed_assignment_uuid = _uuid.UUID(assignment_uuid)
        except ValueError:
            return json.dumps({"error": f"Invalid assignment UUID: {assignment_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        orchestrator, err = await _resolve_orchestrator(ctx, session)
        if err:
            return err

        # Parse tasks
        from app.schemas.agent_invocations import DelegateParallelRequest, ParallelTask

        try:
            parallel_tasks: list[ParallelTask] = []
            for t in tasks:
                child_uuid = _uuid.UUID(t["child_agent_id"])
                parallel_tasks.append(
                    ParallelTask(
                        child_agent_id=child_uuid,
                        task_description=t["task_description"],
                        input_context=t.get("input_context"),
                        output_schema=t.get("output_schema"),
                        timeout_seconds=t.get("timeout_seconds", 300),
                    )
                )
        except (KeyError, ValueError) as exc:
            return json.dumps({"error": f"Invalid task specification: {exc}"})

        request = DelegateParallelRequest(
            alert_id=parsed_alert_uuid,
            tasks=parallel_tasks,
            assignment_id=parsed_assignment_uuid,
        )

        from app.services.invocation_service import InvocationService

        svc = InvocationService(session)
        client_id = _resolve_client_id(ctx)
        try:
            results = await svc.delegate_parallel(
                orchestrator=orchestrator,
                request=request,
                actor_key_prefix=client_id,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        await session.commit()

        return json.dumps(
            {
                "invocations": [
                    {
                        "invocation_id": str(r.invocation_id),
                        "status": r.status,
                        "child_agent_id": str(r.child_agent_id) if r.child_agent_id else None,
                    }
                    for r in results
                ]
            },
            default=_json_serial,
        )


@mcp_server.tool()
async def get_task_result(
    invocation_uuid: str,
    ctx: Context,
    timeout_seconds: int = 30,
) -> str:
    """Poll until an invocation completes and return the result.

    Waits up to timeout_seconds for the invocation to reach a terminal
    state (completed, failed, timed_out). Returns immediately if already
    terminal.

    Args:
        invocation_uuid: UUID of the invocation to poll.
        timeout_seconds: Maximum seconds to wait (default: 30, max: 60).

    Returns:
        JSON with full invocation details including status, result, and error.
    """
    try:
        parsed_uuid = _uuid.UUID(invocation_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {invocation_uuid}"})

    max_wait = min(timeout_seconds, 60)
    terminal_statuses = {"completed", "failed", "timed_out"}
    elapsed = 0.0

    while elapsed <= max_wait:
        async with AsyncSessionLocal() as session:
            scope_err = await check_scope(ctx, session, "agents:read")
            if scope_err:
                return scope_err

            from app.repositories.agent_invocation_repository import AgentInvocationRepository

            repo = AgentInvocationRepository(session)
            invocation = await repo.get_by_uuid(parsed_uuid)
            if invocation is None:
                return json.dumps({"error": f"Invocation not found: {invocation_uuid}"})

            past_deadline = elapsed + _POLL_INTERVAL_SECONDS > max_wait
            if invocation.status in terminal_statuses or past_deadline:
                return json.dumps(
                    {
                        "uuid": str(invocation.uuid),
                        "status": invocation.status,
                        "result": invocation.result,
                        "error": invocation.error,
                        "cost_cents": invocation.cost_cents,
                        "started_at": invocation.started_at.isoformat()
                        if invocation.started_at
                        else None,
                        "completed_at": invocation.completed_at.isoformat()
                        if invocation.completed_at
                        else None,
                        "task_description": invocation.task_description,
                    },
                    default=_json_serial,
                )

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    return json.dumps({"error": f"Timed out waiting for invocation {invocation_uuid}"})


@mcp_server.tool()
async def get_all_results(
    alert_uuid: str,
    ctx: Context,
) -> str:
    """Get all invocation results for an alert from the current orchestrator.

    Returns all invocations the orchestrator created for the given alert,
    including their statuses and results. Useful for gathering specialist
    outputs before synthesizing a final finding.

    Args:
        alert_uuid: UUID of the alert to get invocation results for.

    Returns:
        JSON array of invocation result summaries.
    """
    try:
        parsed_alert_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid alert UUID: {alert_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        orchestrator, err = await _resolve_orchestrator(ctx, session)
        if err:
            return err

        from sqlalchemy import select

        from app.db.models.alert import Alert
        from app.repositories.agent_invocation_repository import AgentInvocationRepository

        alert_result = await session.execute(
            select(Alert).where(Alert.uuid == parsed_alert_uuid)
        )
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            return json.dumps({"error": f"Alert not found: {alert_uuid}"})

        repo = AgentInvocationRepository(session)
        invocations, _ = await repo.list_for_alert(
            alert_id=alert.id,
            parent_agent_id=orchestrator.id,
            page=1,
            page_size=100,
        )

        return json.dumps(
            [
                {
                    "uuid": str(inv.uuid),
                    "status": inv.status,
                    "task_description": inv.task_description,
                    "result": inv.result,
                    "error": inv.error,
                    "cost_cents": inv.cost_cents,
                    "child_agent_id": inv.child_agent_id,
                    "completed_at": inv.completed_at.isoformat()
                    if inv.completed_at
                    else None,
                }
                for inv in invocations
            ],
            default=_json_serial,
        )
