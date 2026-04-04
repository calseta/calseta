"""RoutineRepository — all DB reads/writes for routines, triggers, and runs."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.agent_routine import AgentRoutine
from app.db.models.routine_run import RoutineRun
from app.db.models.routine_trigger import RoutineTrigger
from app.repositories.base import BaseRepository


class RoutineRepository(BaseRepository[AgentRoutine]):
    model = AgentRoutine

    # ------------------------------------------------------------------
    # Routine CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        agent_registration_id: int,
        name: str,
        description: str | None,
        concurrency_policy: str,
        catch_up_policy: str,
        task_template: dict[str, Any],
        max_consecutive_failures: int,
    ) -> AgentRoutine:
        """Create a new AgentRoutine."""
        routine = AgentRoutine(
            uuid=uuid_module.uuid4(),
            agent_registration_id=agent_registration_id,
            name=name,
            description=description,
            status="active",
            concurrency_policy=concurrency_policy,
            catch_up_policy=catch_up_policy,
            task_template=task_template,
            max_consecutive_failures=max_consecutive_failures,
            consecutive_failures=0,
        )
        self._db.add(routine)
        await self._db.flush()
        await self._db.refresh(routine)
        return routine

    async def get_by_uuid(self, uuid: UUID) -> AgentRoutine | None:  # type: ignore[override]
        """Fetch a routine by UUID, eager-loading triggers."""
        result = await self._db.execute(
            select(AgentRoutine)
            .where(AgentRoutine.uuid == uuid)
            .options(selectinload(AgentRoutine.triggers))
        )
        return result.scalar_one_or_none()

    async def list_routines(
        self,
        agent_registration_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentRoutine], int]:
        """Return (routines, total) with optional filters, newest-first."""
        filters = []
        if agent_registration_id is not None:
            filters.append(AgentRoutine.agent_registration_id == agent_registration_id)
        if status is not None:
            filters.append(AgentRoutine.status == status)
        return await self.paginate(
            *filters,
            order_by=AgentRoutine.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def patch(self, routine: AgentRoutine, **kwargs: Any) -> AgentRoutine:
        """Apply partial updates to a routine."""
        for key, value in kwargs.items():
            setattr(routine, key, value)
        await self._db.flush()
        await self._db.refresh(routine)
        return routine

    # ------------------------------------------------------------------
    # Trigger CRUD
    # ------------------------------------------------------------------

    async def create_trigger(
        self,
        routine_id: int,
        kind: str,
        cron_expression: str | None,
        timezone: str | None,
        webhook_replay_window_sec: int | None,
        is_active: bool,
    ) -> RoutineTrigger:
        """Add a trigger to a routine. Generates webhook_public_id for webhook triggers."""
        trigger = RoutineTrigger(
            uuid=uuid_module.uuid4(),
            routine_id=routine_id,
            kind=kind,
            cron_expression=cron_expression,
            timezone=timezone or "UTC",
            webhook_replay_window_sec=webhook_replay_window_sec,
            is_active=is_active,
        )
        if kind == "webhook":
            # Generate a stable public ID for the webhook URL; the signing secret
            # is set separately via set_webhook_secret().
            trigger.webhook_public_id = str(uuid_module.uuid4()).replace("-", "")
        self._db.add(trigger)
        await self._db.flush()
        await self._db.refresh(trigger)
        return trigger

    async def get_trigger_by_uuid(self, uuid: UUID) -> RoutineTrigger | None:
        """Fetch a trigger by UUID."""
        result = await self._db.execute(
            select(RoutineTrigger).where(RoutineTrigger.uuid == uuid)
        )
        return result.scalar_one_or_none()

    async def get_trigger_by_webhook_public_id(self, public_id: str) -> RoutineTrigger | None:
        """Fetch a trigger by its webhook public ID (used during webhook invocation)."""
        result = await self._db.execute(
            select(RoutineTrigger)
            .where(RoutineTrigger.webhook_public_id == public_id)
            .options(selectinload(RoutineTrigger.routine))
        )
        return result.scalar_one_or_none()

    async def patch_trigger(self, trigger: RoutineTrigger, **kwargs: Any) -> RoutineTrigger:
        """Apply partial updates to a trigger."""
        for key, value in kwargs.items():
            setattr(trigger, key, value)
        await self._db.flush()
        await self._db.refresh(trigger)
        return trigger

    async def delete_trigger(self, trigger: RoutineTrigger) -> None:
        """Delete a trigger and flush."""
        await self._db.delete(trigger)
        await self._db.flush()

    async def list_due_cron_triggers(self) -> list[RoutineTrigger]:
        """Return all cron triggers whose next_run_at <= now() and routine is active."""
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(RoutineTrigger)
            .join(AgentRoutine, RoutineTrigger.routine_id == AgentRoutine.id)
            .where(
                RoutineTrigger.kind == "cron",
                RoutineTrigger.is_active.is_(True),
                RoutineTrigger.next_run_at <= now,
                AgentRoutine.status == "active",
            )
            .options(selectinload(RoutineTrigger.routine))
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Run CRUD
    # ------------------------------------------------------------------

    async def create_run(
        self,
        routine_id: int,
        trigger_id: int,
        source: str,
        trigger_payload: dict[str, Any] | None = None,
    ) -> RoutineRun:
        """Create a new RoutineRun in 'received' status."""
        run = RoutineRun(
            uuid=uuid_module.uuid4(),
            routine_id=routine_id,
            trigger_id=trigger_id,
            source=source,
            status="received",
            trigger_payload=trigger_payload,
        )
        self._db.add(run)
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def list_runs(
        self,
        routine_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[RoutineRun], int]:
        """Return (runs, total) for a routine, newest-first."""
        from sqlalchemy import func

        count_result = await self._db.execute(
            select(func.count()).select_from(RoutineRun).where(RoutineRun.routine_id == routine_id)
        )
        total: int = count_result.scalar_one()

        result = await self._db.execute(
            select(RoutineRun)
            .where(RoutineRun.routine_id == routine_id)
            .order_by(RoutineRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(RoutineRun.trigger))
        )
        return list(result.scalars().all()), total

    async def update_run_status(
        self,
        run: RoutineRun,
        status: str,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> RoutineRun:
        """Update a run's status, optional error, and completed_at."""
        run.status = status
        if error is not None:
            run.error = error
        if completed_at is not None:
            run.completed_at = completed_at
        await self._db.flush()
        await self._db.refresh(run)
        return run
