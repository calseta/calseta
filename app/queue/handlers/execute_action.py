"""Handler for execute_response_action_task — execute an approved or auto-approved action."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.queue.handlers.payloads import ExecuteResponseActionPayload
from app.repositories.agent_action_repository import AgentActionRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService

logger = structlog.get_logger(__name__)


class ExecuteResponseActionHandler:
    """Execute an approved or auto-approved agent action.

    1. Load AgentAction from DB.
    2. Guard: status must be "approved" or "executing".
    3. Set status = "executing".
    4. Resolve ActionIntegration from registry.
    5. Call integration.execute(action).
    6. Update action: status = "completed"/"failed", execution_result, executed_at.
    7. Write ACTION_EXECUTED or ACTION_FAILED activity event.
    """

    async def execute(
        self, payload: ExecuteResponseActionPayload, session: AsyncSession
    ) -> None:
        action_repo = AgentActionRepository(session)
        action = await action_repo.get_by_uuid_int_id(payload.agent_action_id)

        if action is None:
            logger.warning(
                "execute_response_action.not_found",
                agent_action_id=payload.agent_action_id,
            )
            return

        # Guard: only execute approved or executing actions
        if action.status not in ("approved", "executing"):
            logger.warning(
                "execute_response_action.wrong_status",
                agent_action_id=action.id,
                status=action.status,
            )
            return

        # Transition to executing
        action.status = "executing"
        await session.flush()

        logger.info(
            "execute_response_action.started",
            action_uuid=str(action.uuid),
            action_type=action.action_type,
            action_subtype=action.action_subtype,
        )

        # Resolve integration
        try:
            from app.integrations.actions.registry import get_integration_for_action

            integration = get_integration_for_action(action.action_subtype, db=session)
            result = await integration.execute(action)
        except Exception as exc:
            logger.exception(
                "execute_response_action.integration_error",
                action_uuid=str(action.uuid),
                error=str(exc),
            )
            from app.integrations.actions.base import ExecutionResult

            result = ExecutionResult.fail(
                f"Unhandled integration error: {exc}",
                {"exception": str(exc)},
            )

        # Persist result
        executed_at = datetime.now(UTC)
        new_status = "completed" if result.success else "failed"
        execution_result = {
            "success": result.success,
            "message": result.message,
            "data": result.data,
        }

        await action_repo.update_status(
            action,
            status=new_status,
            execution_result=execution_result,
            executed_at=executed_at,
        )

        logger.info(
            "execute_response_action.finished",
            action_uuid=str(action.uuid),
            status=new_status,
            success=result.success,
            message=result.message,
        )

        # Write activity event
        try:
            event_type = (
                ActivityEventType.ACTION_EXECUTED
                if result.success
                else ActivityEventType.ACTION_FAILED
            )
            activity_svc = ActivityEventService(session)
            await activity_svc.write(
                event_type,
                actor_type="system",
                alert_id=action.alert_id,
                references={
                    "action_uuid": str(action.uuid),
                    "action_type": action.action_type,
                    "action_subtype": action.action_subtype,
                    "success": result.success,
                    "message": result.message,
                },
            )
        except Exception:
            pass
