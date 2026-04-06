"""RoutineService — business logic for the Routine Scheduler system.

Routines are recurring work patterns for agents: they are triggered by cron
schedules, inbound webhooks, or manual invocation. Each execution produces a
RoutineRun audit record.

Execution flow:
  1. create_routine: validate enums, resolve agent UUID → int ID, persist routine + triggers.
  2. get_routine / list_routines: read-only queries.
  3. patch_routine: validate enums if provided, apply partial update.
  4. delete_routine: cascade-delete via FK.
  5. pause_routine / resume_routine: status transitions.
  6. invoke_routine: find or create a manual trigger, create run, enqueue (Phase 6+).
  7. add_trigger / patch_trigger / delete_trigger: trigger management.
  8. handle_webhook_trigger: HMAC verification → run creation.
  9. list_runs: paginated run history.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.agent_routine import AgentRoutine
from app.db.models.routine_run import RoutineRun
from app.db.models.routine_trigger import RoutineTrigger
from app.repositories.agent_repository import AgentRepository
from app.repositories.routine_repository import RoutineRepository
from app.schemas.routines import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    RoutineCreate,
    RoutineInvokeRequest,
    RoutinePatch,
    RoutineResponse,
    RoutineRunResponse,
    RoutineRunStatus,
    RoutineStatus,
    TriggerCreate,
    TriggerKind,
    TriggerPatch,
    TriggerResponse,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_trigger_response(trigger: RoutineTrigger) -> TriggerResponse:
    return TriggerResponse(
        uuid=trigger.uuid,
        kind=trigger.kind,
        cron_expression=trigger.cron_expression,
        timezone=trigger.timezone,
        webhook_public_id=trigger.webhook_public_id,
        next_run_at=trigger.next_run_at,
        last_fired_at=trigger.last_fired_at,
        is_active=trigger.is_active,
        created_at=trigger.created_at,
    )


def _build_routine_response(routine: AgentRoutine) -> RoutineResponse:
    return RoutineResponse(
        uuid=routine.uuid,
        name=routine.name,
        description=routine.description,
        status=routine.status,
        concurrency_policy=routine.concurrency_policy,
        catch_up_policy=routine.catch_up_policy,
        task_template=routine.task_template,
        max_consecutive_failures=routine.max_consecutive_failures,
        consecutive_failures=routine.consecutive_failures,
        last_run_at=routine.last_run_at,
        next_run_at=routine.next_run_at,
        created_at=routine.created_at,
        updated_at=routine.updated_at,
        agent_registration_uuid=routine.agent_registration.uuid
        if routine.agent_registration
        else None,
        triggers=[_build_trigger_response(t) for t in (routine.triggers or [])],
    )


def _build_run_response(run: RoutineRun) -> RoutineRunResponse:
    trigger_uuid = run.trigger.uuid if run.trigger else None
    return RoutineRunResponse(
        uuid=run.uuid,
        source=run.source,
        status=run.status,
        trigger_payload=run.trigger_payload,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
        trigger_uuid=trigger_uuid,
    )


def _validate_concurrency_policy(value: str) -> None:
    if value not in ConcurrencyPolicy.ALL:
        raise CalsetaException(
            code="INVALID_CONCURRENCY_POLICY",
            message=f"concurrency_policy must be one of {ConcurrencyPolicy.ALL}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _validate_catch_up_policy(value: str) -> None:
    if value not in CatchUpPolicy.ALL:
        raise CalsetaException(
            code="INVALID_CATCH_UP_POLICY",
            message=f"catch_up_policy must be one of {CatchUpPolicy.ALL}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _validate_trigger_kind(value: str) -> None:
    if value not in TriggerKind.ALL:
        raise CalsetaException(
            code="INVALID_TRIGGER_KIND",
            message=f"trigger kind must be one of {TriggerKind.ALL}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _verify_webhook_signature(
    secret: str,
    body: bytes,
    signature: str,
    timestamp: str,
) -> bool:
    """Verify HMAC-SHA256 webhook signature.

    Signature format: sha256=<hex>
    Message format: "{timestamp}." + raw body bytes

    NOTE: webhook_secret_hash stores the raw signing secret (not a bcrypt hash).
    The field name is legacy from the original spec; in v1 we store plaintext
    for HMAC verification. Rotate secrets by patching the trigger.
    """
    try:
        int(timestamp)
    except (ValueError, TypeError):
        return False

    msg = f"{timestamp}.".encode() + body
    expected = "sha256=" + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class RoutineService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_routine(self, data: RoutineCreate) -> RoutineResponse:
        """Validate enums, resolve agent UUID, create routine and any triggers."""
        _validate_concurrency_policy(data.concurrency_policy)
        _validate_catch_up_policy(data.catch_up_policy)

        agent_repo = AgentRepository(self._db)
        agent = await agent_repo.get_by_uuid(data.agent_registration_uuid)
        if agent is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Agent registration {data.agent_registration_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        repo = RoutineRepository(self._db)
        routine = await repo.create(
            agent_registration_id=agent.id,
            name=data.name,
            description=data.description,
            concurrency_policy=data.concurrency_policy,
            catch_up_policy=data.catch_up_policy,
            task_template=data.task_template,
            max_consecutive_failures=data.max_consecutive_failures,
        )

        for trigger_data in data.triggers:
            await self._create_trigger_for_routine(repo, routine.id, trigger_data)

        # Reload with triggers + agent_registration eager-loaded
        routine = await repo.get_by_uuid(routine.uuid)  # type: ignore[assignment]
        await self._db.refresh(routine, ["agent_registration"])

        logger.info(
            "routine.created",
            routine_uuid=str(routine.uuid),
            agent_uuid=str(data.agent_registration_uuid),
        )
        return _build_routine_response(routine)

    async def get_routine(self, routine_uuid: UUID) -> RoutineResponse:
        """Fetch a routine by UUID; raises 404 if not found."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        await self._db.refresh(routine, ["agent_registration"])
        return _build_routine_response(routine)

    async def list_routines(
        self,
        agent_uuid: UUID | None,
        routine_status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RoutineResponse], int]:
        """Return (routines, total) with optional filters."""
        agent_id: int | None = None
        if agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(agent_uuid)
            if agent is None:
                raise CalsetaException(
                    code="NOT_FOUND",
                    message=f"Agent registration {agent_uuid} not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            agent_id = agent.id

        repo = RoutineRepository(self._db)
        routines, total = await repo.list_routines(
            agent_registration_id=agent_id,
            status=routine_status,
            page=page,
            page_size=page_size,
        )

        # Eager-load agent_registration for each routine
        for r in routines:
            await self._db.refresh(r, ["agent_registration", "triggers"])

        return [_build_routine_response(r) for r in routines], total

    async def patch_routine(self, routine_uuid: UUID, patch: RoutinePatch) -> RoutineResponse:
        """Apply partial updates to a routine."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        updates: dict[str, Any] = {}
        if patch.name is not None:
            updates["name"] = patch.name
        if patch.description is not None:
            updates["description"] = patch.description
        if patch.status is not None:
            if patch.status not in RoutineStatus.ALL:
                raise CalsetaException(
                    code="INVALID_STATUS",
                    message=f"Invalid status '{patch.status}'. Must be one of: {', '.join(RoutineStatus.ALL)}.",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            updates["status"] = patch.status
        if patch.concurrency_policy is not None:
            _validate_concurrency_policy(patch.concurrency_policy)
            updates["concurrency_policy"] = patch.concurrency_policy
        if patch.catch_up_policy is not None:
            _validate_catch_up_policy(patch.catch_up_policy)
            updates["catch_up_policy"] = patch.catch_up_policy
        if patch.task_template is not None:
            updates["task_template"] = patch.task_template
        if patch.max_consecutive_failures is not None:
            updates["max_consecutive_failures"] = patch.max_consecutive_failures

        if updates:
            routine = await repo.patch(routine, **updates)

        await self._db.refresh(routine, ["agent_registration"])
        return _build_routine_response(routine)

    async def delete_routine(self, routine_uuid: UUID) -> None:
        """Delete a routine (cascades to triggers and runs)."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        await repo.delete(routine)
        logger.info("routine.deleted", routine_uuid=str(routine_uuid))

    async def pause_routine(self, routine_uuid: UUID) -> RoutineResponse:
        """Transition a routine to paused status."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if routine.status == RoutineStatus.PAUSED:
            raise CalsetaException(
                code="ALREADY_PAUSED",
                message="Routine is already paused.",
                status_code=status.HTTP_409_CONFLICT,
            )
        routine = await repo.patch(routine, status=RoutineStatus.PAUSED)
        await self._db.refresh(routine, ["agent_registration"])
        logger.info("routine.paused", routine_uuid=str(routine_uuid))
        return _build_routine_response(routine)

    async def resume_routine(self, routine_uuid: UUID) -> RoutineResponse:
        """Transition a routine to active status."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if routine.status == RoutineStatus.ACTIVE:
            raise CalsetaException(
                code="ALREADY_ACTIVE",
                message="Routine is already active.",
                status_code=status.HTTP_409_CONFLICT,
            )
        routine = await repo.patch(routine, status=RoutineStatus.ACTIVE)
        await self._db.refresh(routine, ["agent_registration"])
        logger.info("routine.resumed", routine_uuid=str(routine_uuid))
        return _build_routine_response(routine)

    async def invoke_routine(
        self,
        routine_uuid: UUID,
        invoke_request: RoutineInvokeRequest,
    ) -> RoutineRunResponse:
        """Manually trigger a routine.

        Finds an existing manual trigger or creates one if none exists, then
        creates a RoutineRun in 'enqueued' status. Agent wakeup is Phase 6+.
        """
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Auto-pause if consecutive failures have reached the threshold
        max_failures = routine.max_consecutive_failures or 0
        if max_failures > 0 and routine.consecutive_failures >= max_failures:
            routine.status = RoutineStatus.PAUSED
            await self._db.flush()
            logger.warning(
                "routine.auto_paused",
                routine_uuid=str(routine_uuid),
                consecutive_failures=routine.consecutive_failures,
                max_consecutive_failures=max_failures,
            )

        # Find or create a manual trigger
        manual_trigger: RoutineTrigger | None = next(
            (t for t in routine.triggers if t.kind == TriggerKind.MANUAL), None
        )
        if manual_trigger is None:
            manual_trigger = await repo.create_trigger(
                routine_id=routine.id,
                kind=TriggerKind.MANUAL,
                cron_expression=None,
                timezone=None,
                webhook_replay_window_sec=None,
                is_active=True,
            )

        run = await repo.create_run(
            routine_id=routine.id,
            trigger_id=manual_trigger.id,
            source=TriggerKind.MANUAL,
            trigger_payload=invoke_request.payload,
        )
        # Advance to enqueued — actual execution wired in Phase 6+
        run = await repo.update_run_status(run, status=RoutineRunStatus.ENQUEUED)

        logger.info(
            "routine.invoked",
            routine_uuid=str(routine_uuid),
            run_uuid=str(run.uuid),
        )
        await self._db.refresh(run, ["trigger"])
        return _build_run_response(run)

    async def add_trigger(
        self,
        routine_uuid: UUID,
        data: TriggerCreate,
    ) -> TriggerResponse:
        """Validate and add a trigger to a routine."""
        _validate_trigger_kind(data.kind)

        if data.kind == TriggerKind.CRON and not data.cron_expression:
            raise CalsetaException(
                code="MISSING_CRON_EXPRESSION",
                message="cron_expression is required for cron triggers.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        trigger = await self._create_trigger_for_routine(repo, routine.id, data)
        logger.info(
            "routine.trigger.added",
            routine_uuid=str(routine_uuid),
            trigger_uuid=str(trigger.uuid),
            kind=data.kind,
        )
        return _build_trigger_response(trigger)

    async def patch_trigger(
        self,
        routine_uuid: UUID,
        trigger_uuid: UUID,
        data: TriggerPatch,
    ) -> TriggerResponse:
        """Apply partial updates to a trigger after verifying routine ownership."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        trigger = await repo.get_trigger_by_uuid(trigger_uuid)
        if trigger is None or trigger.routine_id != routine.id:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Trigger {trigger_uuid} not found on routine {routine_uuid}.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        updates: dict[str, Any] = {}
        if data.cron_expression is not None:
            updates["cron_expression"] = data.cron_expression
        if data.timezone is not None:
            updates["timezone"] = data.timezone
        if data.webhook_replay_window_sec is not None:
            updates["webhook_replay_window_sec"] = data.webhook_replay_window_sec
        if data.is_active is not None:
            updates["is_active"] = data.is_active

        if updates:
            trigger = await repo.patch_trigger(trigger, **updates)

        return _build_trigger_response(trigger)

    async def delete_trigger(
        self,
        routine_uuid: UUID,
        trigger_uuid: UUID,
    ) -> None:
        """Delete a trigger after verifying routine ownership."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        trigger = await repo.get_trigger_by_uuid(trigger_uuid)
        if trigger is None or trigger.routine_id != routine.id:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Trigger {trigger_uuid} not found on routine {routine_uuid}.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        await repo.delete_trigger(trigger)
        logger.info(
            "routine.trigger.deleted",
            routine_uuid=str(routine_uuid),
            trigger_uuid=str(trigger_uuid),
        )

    async def handle_webhook_trigger(
        self,
        routine_uuid: UUID,
        trigger_uuid: UUID,
        body: bytes,
        signature: str | None,
        timestamp: str | None,
    ) -> RoutineRunResponse:
        """Verify HMAC signature and create a run for an inbound webhook trigger.

        Raises 401 if signature verification fails.
        Raises 422 if the replay window is exceeded.
        """
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        trigger = await repo.get_trigger_by_uuid(trigger_uuid)
        if trigger is None or trigger.routine_id != routine.id:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Trigger {trigger_uuid} not found on routine {routine_uuid}.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if trigger.kind != TriggerKind.WEBHOOK:
            raise CalsetaException(
                code="INVALID_TRIGGER_KIND",
                message="This trigger is not a webhook trigger.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not trigger.is_active:
            raise CalsetaException(
                code="TRIGGER_INACTIVE",
                message="This webhook trigger is inactive.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # HMAC verification — only if a secret is configured
        if trigger.webhook_secret_hash:
            if not signature or not timestamp:
                raise CalsetaException(
                    code="MISSING_SIGNATURE",
                    message="X-Signature and X-Timestamp headers are required.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            # Replay window check
            try:
                ts_int = int(timestamp)
                if abs(time.time() - ts_int) > (trigger.webhook_replay_window_sec or 300):
                    raise CalsetaException(
                        code="REPLAY_WINDOW_EXCEEDED",
                        message="Request timestamp is outside the replay window.",
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
            except (ValueError, TypeError) as err:
                raise CalsetaException(
                    code="INVALID_TIMESTAMP",
                    message="X-Timestamp must be a Unix epoch integer.",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                ) from err

            if not _verify_webhook_signature(
                secret=trigger.webhook_secret_hash,
                body=body,
                signature=signature,
                timestamp=timestamp,
            ):
                raise CalsetaException(
                    code="INVALID_SIGNATURE",
                    message="Webhook signature verification failed.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        # Parse payload for storage (best-effort)
        import json
        trigger_payload: dict[str, Any] | None = None
        try:
            trigger_payload = json.loads(body) if body else None
        except (json.JSONDecodeError, ValueError):
            trigger_payload = {"raw": body.decode("utf-8", errors="replace")}

        run = await repo.create_run(
            routine_id=routine.id,
            trigger_id=trigger.id,
            source=TriggerKind.WEBHOOK,
            trigger_payload=trigger_payload,
        )
        run = await repo.update_run_status(run, status=RoutineRunStatus.ENQUEUED)

        # Update trigger last_fired_at
        await repo.patch_trigger(trigger, last_fired_at=datetime.now(UTC))

        logger.info(
            "routine.webhook_trigger.fired",
            routine_uuid=str(routine_uuid),
            trigger_uuid=str(trigger_uuid),
            run_uuid=str(run.uuid),
        )
        await self._db.refresh(run, ["trigger"])
        return _build_run_response(run)

    async def list_runs(
        self,
        routine_uuid: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[RoutineRunResponse], int]:
        """Return (runs, total) for a routine."""
        repo = RoutineRepository(self._db)
        routine = await repo.get_by_uuid(routine_uuid)
        if routine is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Routine {routine_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        runs, total = await repo.list_runs(
            routine_id=routine.id,
            page=page,
            page_size=page_size,
        )
        return [_build_run_response(r) for r in runs], total

    async def evaluate_cron_triggers(self) -> int:
        """Evaluate all due cron triggers and create routine_runs.

        Called by the periodic queue task every minute.

        Croniter is not available — after firing a trigger, next_run_at is
        cleared (set to None) so the trigger will not re-fire until it is
        reset externally. Operators should use the PATCH trigger endpoint to
        set next_run_at for the next occurrence, or a future croniter
        integration can compute it automatically.

        Returns:
            Number of triggers fired.
        """
        repo = RoutineRepository(self._db)
        due_triggers = await repo.list_due_cron_triggers()
        fired = 0

        for trigger in due_triggers:
            routine = trigger.routine

            # Concurrency policy: skip if an active (non-terminal) run exists
            if routine.concurrency_policy == "skip_if_active":
                from sqlalchemy import func, select

                from app.db.models.routine_run import RoutineRun

                active_count_result = await self._db.execute(
                    select(func.count())
                    .select_from(RoutineRun)
                    .where(
                        RoutineRun.routine_id == routine.id,
                        RoutineRun.status.notin_(["completed", "failed", "cancelled"]),
                    )
                )
                active_count: int = active_count_result.scalar_one()
                if active_count > 0:
                    logger.info(
                        "routine.cron_trigger.skipped",
                        trigger_uuid=str(trigger.uuid),
                        routine_uuid=str(routine.uuid),
                        reason="active_run_exists",
                    )
                    # Still clear next_run_at so we don't keep re-skipping every minute
                    await repo.patch_trigger(
                        trigger,
                        last_fired_at=datetime.now(UTC),
                        next_run_at=None,
                    )
                    continue

            # Create the run
            run = await repo.create_run(
                routine_id=routine.id,
                trigger_id=trigger.id,
                source="cron",
            )
            await repo.update_run_status(run, status=RoutineRunStatus.ENQUEUED)

            # Update trigger metadata
            now = datetime.now(UTC)
            await repo.patch_trigger(
                trigger,
                last_fired_at=now,
                next_run_at=None,  # cleared — croniter not available; operator resets
            )

            fired += 1
            logger.info(
                "routine.cron_trigger.fired",
                trigger_uuid=str(trigger.uuid),
                routine_uuid=str(routine.uuid),
                run_uuid=str(run.uuid),
            )

        if fired > 0:
            await self._db.commit()

        return fired

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _create_trigger_for_routine(
        self,
        repo: RoutineRepository,
        routine_id: int,
        data: TriggerCreate,
    ) -> RoutineTrigger:
        """Validate trigger kind and create. Called from create_routine and add_trigger."""
        _validate_trigger_kind(data.kind)
        if data.kind == TriggerKind.CRON and not data.cron_expression:
            raise CalsetaException(
                code="MISSING_CRON_EXPRESSION",
                message="cron_expression is required for cron triggers.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return await repo.create_trigger(
            routine_id=routine_id,
            kind=data.kind,
            cron_expression=data.cron_expression,
            timezone=data.timezone,
            webhook_replay_window_sec=data.webhook_replay_window_sec,
            is_active=data.is_active,
        )
