"""WorkflowRun repository — execution audit log reads/writes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow_run import WorkflowRun


class WorkflowRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        workflow_id: int,
        trigger_type: str,
        trigger_context: dict[str, Any] | None,
        code_version_executed: int,
        status: str = "queued",
    ) -> WorkflowRun:
        run = WorkflowRun(
            uuid=uuid.uuid4(),
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_context=trigger_context,
            code_version_executed=code_version_executed,
            status=status,
            attempt_count=0,
        )
        self._db.add(run)
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def get_by_uuid(self, run_uuid: uuid.UUID) -> WorkflowRun | None:
        result = await self._db.execute(
            select(WorkflowRun).where(WorkflowRun.uuid == run_uuid)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, run_id: int) -> WorkflowRun | None:
        result = await self._db.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_for_workflow(
        self,
        workflow_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowRun], int]:
        from sqlalchemy import func

        count_stmt = (
            select(func.count())
            .select_from(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
        )
        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(WorkflowRun.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def list_all(
        self,
        *,
        status: str | None = None,
        workflow_id: int | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowRun], int]:
        from sqlalchemy import func

        stmt = select(WorkflowRun)
        count_stmt = select(func.count()).select_from(WorkflowRun)

        if status is not None:
            stmt = stmt.where(WorkflowRun.status == status)
            count_stmt = count_stmt.where(WorkflowRun.status == status)
        if workflow_id is not None:
            stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
            count_stmt = count_stmt.where(WorkflowRun.workflow_id == workflow_id)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(WorkflowRun.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def update_after_execution(
        self,
        run: WorkflowRun,
        *,
        status: str,
        log_output: str | None,
        result_data: dict[str, Any] | None,
        duration_ms: int,
        completed_at: str,
    ) -> WorkflowRun:
        run.status = status
        run.log_output = log_output
        run.result = result_data
        run.duration_ms = duration_ms
        run.completed_at = completed_at
        run.attempt_count = run.attempt_count + 1
        await self._db.flush()
        await self._db.refresh(run)
        return run
