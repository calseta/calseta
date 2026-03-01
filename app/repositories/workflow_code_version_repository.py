"""Repository for workflow_code_versions table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow_code_version import WorkflowCodeVersion


class WorkflowCodeVersionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_version(
        self,
        workflow_id: int,
        version: int,
        code: str,
    ) -> WorkflowCodeVersion:
        """Persist a code snapshot before incrementing code_version."""
        entry = WorkflowCodeVersion(
            workflow_id=workflow_id,
            version=version,
            code=code,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def list_for_workflow(self, workflow_id: int) -> list[WorkflowCodeVersion]:
        """Return all versions for a workflow ordered by version descending."""
        result = await self._db.execute(
            select(WorkflowCodeVersion)
            .where(WorkflowCodeVersion.workflow_id == workflow_id)
            .order_by(WorkflowCodeVersion.version.desc())
        )
        return list(result.scalars().all())
