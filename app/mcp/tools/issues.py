"""MCP tools for the Issue/Task system.

Tools:
  - create_issue         — Create a new follow-up issue (agents:write)
  - get_my_issues        — Get issues assigned to this agent (agents:read)
  - update_issue_status  — Update issue status (agents:write)
  - add_issue_comment    — Add a comment to an issue (agents:write)
  - checkout_issue       — Atomic checkout of an issue (agents:write)
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def create_issue(
    title: str,
    ctx: Context,
    description: str | None = None,
    priority: str = "medium",
    category: str = "investigation",
    assignee_agent_uuid: str | None = None,
    alert_uuid: str | None = None,
) -> str:
    """Create a new issue/task linked optionally to an alert.

    Args:
        title: Short title for the issue (required).
        description: Detailed description of the work to be done.
        priority: Priority level — "critical", "high", "medium" (default), "low".
        category: Issue category — "investigation", "remediation", "detection_tuning",
                  "compliance", "post_incident", "maintenance", "custom".
        assignee_agent_uuid: UUID of the agent to assign the issue to.
        alert_uuid: UUID of an alert to link this issue to.

    Returns:
        JSON with the created issue UUID and identifier.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.issues import IssueCreate
        from app.services.issue_service import IssueService

        parsed_assignee: _uuid.UUID | None = None
        if assignee_agent_uuid:
            try:
                parsed_assignee = _uuid.UUID(assignee_agent_uuid)
            except ValueError:
                return json.dumps({"error": f"Invalid assignee_agent_uuid: {assignee_agent_uuid}"})

        parsed_alert: _uuid.UUID | None = None
        if alert_uuid:
            try:
                parsed_alert = _uuid.UUID(alert_uuid)
            except ValueError:
                return json.dumps({"error": f"Invalid alert_uuid: {alert_uuid}"})

        data = IssueCreate(
            title=title,
            description=description,
            priority=priority,
            category=category,
            assignee_agent_uuid=parsed_assignee,
            alert_uuid=parsed_alert,
        )

        try:
            svc = IssueService(session)
            issue = await svc.create_issue(data=data)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(issue.uuid),
            "identifier": issue.identifier,
            "title": issue.title,
            "status": issue.status,
            "priority": issue.priority,
            "category": issue.category,
            "created_at": issue.created_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def get_my_issues(
    ctx: Context,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Get issues assigned to the calling agent.

    Args:
        status: Filter by status (e.g. "backlog", "in_progress", "done").
                Omit to return all statuses.
        page: Page number (1-indexed, default 1).
        page_size: Results per page (default 20, max 100).

    Returns:
        JSON list of issues assigned to this agent.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        client_id = _resolve_client_id(ctx)
        if not client_id:
            return json.dumps({"error": "Cannot resolve agent identity from context."})

        # Resolve agent from API key prefix
        from sqlalchemy import select

        from app.db.models.agent_api_key import AgentAPIKey
        from app.db.models.agent_registration import AgentRegistration

        key_result = await session.execute(
            select(AgentAPIKey).where(AgentAPIKey.key_prefix == client_id)
        )
        agent_key = key_result.scalar_one_or_none()
        if agent_key is None:
            return json.dumps({"error": "Agent API key not found."})

        agent_result = await session.execute(
            select(AgentRegistration).where(
                AgentRegistration.id == agent_key.agent_registration_id
            )
        )
        agent = agent_result.scalar_one_or_none()
        if agent is None:
            return json.dumps({"error": "Agent registration not found."})

        from app.services.issue_service import IssueService

        page_size = min(page_size, 100)
        svc = IssueService(session)
        issues, total = await svc.list_agent_issues(
            agent_uuid=agent.uuid,
            page=page,
            page_size=page_size,
        )
        if status:
            issues = [i for i in issues if i.status == status]

        result = [
            {
                "uuid": str(i.uuid),
                "identifier": i.identifier,
                "title": i.title,
                "status": i.status,
                "priority": i.priority,
                "category": i.category,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "alert_uuid": str(i.alert_uuid) if i.alert_uuid else None,
                "created_at": i.created_at.isoformat(),
            }
            for i in issues
        ]
        return json.dumps({
            "issues": result,
            "total": total,
            "page": page,
            "page_size": page_size,
        }, default=_json_serial)


@mcp_server.tool()
async def update_issue_status(
    issue_uuid: str,
    status: str,
    ctx: Context,
    resolution: str | None = None,
) -> str:
    """Update the status of an issue.

    Args:
        issue_uuid: UUID of the issue to update.
        status: New status — "backlog", "todo", "in_progress", "in_review",
                "done", "blocked", "cancelled".
        resolution: Optional resolution note (recommended when setting status to "done").

    Returns:
        JSON with the updated issue UUID and new status.
    """
    try:
        parsed_uuid = _uuid.UUID(issue_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {issue_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.issues import IssuePatch
        from app.services.issue_service import IssueService

        patch = IssuePatch(status=status, resolution=resolution)
        try:
            svc = IssueService(session)
            issue = await svc.patch_issue(parsed_uuid, patch)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(issue.uuid),
            "identifier": issue.identifier,
            "status": issue.status,
            "resolution": issue.resolution,
        }, default=_json_serial)


@mcp_server.tool()
async def add_issue_comment(
    issue_uuid: str,
    body: str,
    ctx: Context,
) -> str:
    """Add a comment to an issue.

    Args:
        issue_uuid: UUID of the issue to comment on.
        body: Comment body text (required, must be non-empty).

    Returns:
        JSON with the created comment UUID and timestamp.
    """
    try:
        parsed_uuid = _uuid.UUID(issue_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {issue_uuid}"})

    if not body.strip():
        return json.dumps({"error": "Comment body cannot be empty."})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.issues import IssueCommentCreate
        from app.services.issue_service import IssueService

        data = IssueCommentCreate(body=body)
        try:
            svc = IssueService(session)
            comment = await svc.add_comment(issue_uuid=parsed_uuid, data=data)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(comment.uuid),
            "issue_uuid": issue_uuid,
            "created_at": comment.created_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def checkout_issue(
    issue_uuid: str,
    heartbeat_run_uuid: str,
    ctx: Context,
) -> str:
    """Atomically lock an issue for exclusive processing.

    Prevents two agents from working on the same issue simultaneously.
    Returns 409 if the issue is already checked out.

    Args:
        issue_uuid: UUID of the issue to check out.
        heartbeat_run_uuid: UUID of the current heartbeat run (proves liveness).

    Returns:
        JSON with the checked-out issue details, or an error if already locked.
    """
    try:
        parsed_issue_uuid = _uuid.UUID(issue_uuid)
        parsed_run_uuid = _uuid.UUID(heartbeat_run_uuid)
    except ValueError as exc:
        return json.dumps({"error": f"Invalid UUID: {exc}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.services.issue_service import IssueService

        try:
            svc = IssueService(session)
            issue = await svc.checkout_issue(parsed_issue_uuid, parsed_run_uuid)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(issue.uuid),
            "identifier": issue.identifier,
            "status": issue.status,
            "checked_out": True,
        }, default=_json_serial)
