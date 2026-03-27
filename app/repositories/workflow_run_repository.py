"""WorkflowRun repository — execution audit log reads/writes."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.models.workflow_run import WorkflowRun
from app.repositories.base import BaseRepository


class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    model = WorkflowRun

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

    async def list_for_workflow(
        self,
        workflow_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkflowRun], int]:
        return await self.paginate(
            WorkflowRun.workflow_id == workflow_id,
            order_by=WorkflowRun.created_at.desc(),
            page=page,
            page_size=page_size,
        )

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
        filters = []
        if status is not None:
            filters.append(WorkflowRun.status == status)
        if workflow_id is not None:
            filters.append(WorkflowRun.workflow_id == workflow_id)

        return await self.paginate(
            *filters,
            order_by=WorkflowRun.created_at.desc(),
            page=page,
            page_size=page_size,
        )

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
