"""ExecuteInvocationHandler — run a specialist agent for a delegated invocation.

For webhook-mode specialists: POST the task payload to the specialist's endpoint
and record the result. For managed-agent specialists: create an assignment and
enqueue the managed agent task. No LLM tokens consumed here — deterministic execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_invocation import AgentInvocation
from app.queue.handlers.payloads import ExecuteInvocationPayload

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class ExecuteInvocationHandler:
    """Execute a single agent invocation task."""

    async def execute(
        self,
        payload: ExecuteInvocationPayload,
        db: AsyncSession,
    ) -> None:
        from datetime import UTC, datetime

        from app.repositories.agent_invocation_repository import AgentInvocationRepository
        from app.repositories.agent_repository import AgentRepository
        from app.schemas.activity_events import ActivityEventType

        repo = AgentInvocationRepository(db)
        invocation = await repo.get_by_id(payload.invocation_id)
        if invocation is None:
            logger.warning(
                "execute_invocation.not_found",
                invocation_id=payload.invocation_id,
            )
            return

        # Idempotency: skip if already terminal
        if invocation.status in ("completed", "failed", "timed_out"):
            logger.info(
                "execute_invocation.already_terminal",
                invocation_uuid=str(invocation.uuid),
                status=invocation.status,
            )
            return

        now = datetime.now(UTC)
        await repo.update_status(invocation, "running", started_at=now)

        agent_repo = AgentRepository(db)
        child_agent = None
        if invocation.child_agent_id is not None:
            child_agent = await agent_repo.get_by_id(invocation.child_agent_id)

        if child_agent is None:
            await repo.update_status(
                invocation,
                "failed",
                error="Specialist agent not found or not assigned.",
                completed_at=datetime.now(UTC),
            )
            await _write_activity(db, invocation, ActivityEventType.INVOCATION_FAILED)
            return

        # Dispatch based on adapter type
        if child_agent.execution_mode == "external" and child_agent.endpoint_url:
            result, error = await _call_webhook_specialist(invocation, child_agent)
        else:
            result, error = await _enqueue_managed_specialist(invocation, child_agent, db)

        completed_at = datetime.now(UTC)
        if error:
            await repo.update_status(
                invocation,
                "failed",
                error=error,
                completed_at=completed_at,
            )
            await _write_activity(db, invocation, ActivityEventType.INVOCATION_FAILED)
        else:
            await repo.update_status(
                invocation,
                "completed",
                result=result,
                completed_at=completed_at,
            )
            await _write_activity(db, invocation, ActivityEventType.INVOCATION_COMPLETED)

        logger.info(
            "execute_invocation.done",
            invocation_uuid=str(invocation.uuid),
            status=invocation.status,
            child_agent=child_agent.name,
        )


async def _call_webhook_specialist(
    invocation: AgentInvocation,
    child_agent: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """POST invocation payload to a webhook-mode specialist. Returns (result, error)."""
    import json

    import httpx

    from app.auth.encryption import decrypt_value
    from app.config import settings
    from app.services.url_validation import is_safe_outbound_url

    endpoint_url: str = child_agent.endpoint_url
    safe, reason = is_safe_outbound_url(endpoint_url)
    if not safe:
        return None, f"SSRF blocked: {reason}"

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if child_agent.auth_header_name and child_agent.auth_header_value_encrypted:
        try:
            decrypted = decrypt_value(child_agent.auth_header_value_encrypted)
            headers[child_agent.auth_header_name] = decrypted
        except Exception:
            pass  # no encryption key — send without auth

    payload_body = {
        "invocation_uuid": str(invocation.uuid),
        "task_description": invocation.task_description,
        "input_context": invocation.input_context,
        "output_schema": invocation.output_schema,
        "alert_id": invocation.alert_id,
        "calseta_api_base_url": settings.CALSETA_API_BASE_URL,
    }

    timeout_seconds = min(invocation.timeout_seconds, 300)

    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
            resp = await client.post(endpoint_url, json=payload_body, headers=headers)
        if resp.is_success:
            try:
                return resp.json(), None
            except json.JSONDecodeError:
                return {"raw": resp.text}, None
        else:
            return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.TimeoutException:
        return None, f"Specialist timed out after {timeout_seconds}s"
    except httpx.RequestError as exc:
        return None, f"Connection error: {exc}"


async def _enqueue_managed_specialist(
    invocation: AgentInvocation,
    child_agent: Any,
    db: AsyncSession,
) -> tuple[dict[str, Any] | None, str | None]:
    """For managed-agent specialists: create an assignment and enqueue a heartbeat run.

    Returns immediately with a delegated result; completion is async.
    """
    try:
        from app.repositories.alert_assignment_repository import AlertAssignmentRepository

        assign_repo = AlertAssignmentRepository(db)
        assignment = await assign_repo.atomic_checkout(
            alert_id=invocation.alert_id,
            agent_registration_id=child_agent.id,
        )
        if assignment is None:
            return (
                None,
                "Managed specialist could not check out assignment (alert not available)",
            )

        return {
            "delegated_to_managed_agent": True,
            "child_assignment_id": assignment.id,
        }, None
    except Exception as exc:
        return None, f"Managed agent delegation failed: {exc}"


async def _write_activity(
    db: AsyncSession,
    invocation: AgentInvocation,
    event_type: Any,
) -> None:
    """Write an activity event for this invocation lifecycle step."""
    try:
        from app.services.activity_event import ActivityEventService

        activity_svc = ActivityEventService(db)
        await activity_svc.write(
            event_type,
            actor_type="system",
            actor_key_prefix=None,
            alert_id=invocation.alert_id,
            references={
                "invocation_uuid": str(invocation.uuid),
                "parent_agent_id": invocation.parent_agent_id,
                "child_agent_id": invocation.child_agent_id,
                "status": invocation.status,
            },
        )
    except Exception:
        logger.exception("invocation_activity_write_failed")
