"""
MCP resources for workflows.

Exposes workflow data as MCP resources for AI agent consumption:
  - calseta://workflows         — Full workflow catalog with documentation
  - calseta://workflows/{uuid}  — Full workflow with code and complete configuration
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server
from app.repositories.workflow_repository import WorkflowRepository


def _json_serial(obj: object) -> str:
    """JSON serializer for objects not handled by default json encoder."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.resource("calseta://workflows")
async def list_workflows(ctx: Context) -> str:
    """Workflow catalog with documentation so agents can reason about available automations."""
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "workflows:read")
        if scope_err:
            return scope_err

        repo = WorkflowRepository(session)
        workflows, _total = await repo.list_workflows(page=1, page_size=500)

        result = [
            {
                "uuid": str(wf.uuid),
                "name": wf.name,
                "workflow_type": wf.workflow_type,
                "indicator_types": wf.indicator_types,
                "state": wf.state,
                "code_version": wf.code_version,
                "is_active": wf.is_active,
                "is_system": wf.is_system,
                "tags": wf.tags,
                "time_saved_minutes": wf.time_saved_minutes,
                "approval_mode": wf.approval_mode,
                "risk_level": wf.risk_level,
                "documentation": wf.documentation,
                "created_at": wf.created_at.isoformat(),
                "updated_at": wf.updated_at.isoformat(),
            }
            for wf in workflows
        ]

        return json.dumps(
            {"workflows": result, "count": len(result)},
            default=_json_serial,
        )


@mcp_server.resource("calseta://workflows/{uuid}")
async def get_workflow(uuid: str, ctx: Context) -> str:
    """Full workflow with code, documentation, and complete approval configuration."""
    try:
        workflow_uuid = _uuid.UUID(uuid)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID: {uuid}") from exc

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "workflows:read")
        if scope_err:
            return scope_err

        repo = WorkflowRepository(session)
        wf = await repo.get_by_uuid(workflow_uuid)
        if wf is None:
            raise ValueError(f"Workflow not found: {uuid}")

        result = {
            "uuid": str(wf.uuid),
            "name": wf.name,
            "workflow_type": wf.workflow_type,
            "indicator_types": wf.indicator_types,
            "code": wf.code,
            "code_version": wf.code_version,
            "state": wf.state,
            "timeout_seconds": wf.timeout_seconds,
            "retry_count": wf.retry_count,
            "is_active": wf.is_active,
            "is_system": wf.is_system,
            "tags": wf.tags,
            "time_saved_minutes": wf.time_saved_minutes,
            "approval_mode": wf.approval_mode,
            "approval_channel": wf.approval_channel,
            "approval_timeout_seconds": wf.approval_timeout_seconds,
            "risk_level": wf.risk_level,
            "documentation": wf.documentation,
            "created_at": wf.created_at.isoformat(),
            "updated_at": wf.updated_at.isoformat(),
        }

        return json.dumps(result, default=_json_serial)
