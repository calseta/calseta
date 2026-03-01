"""Workflow repository — all DB reads/writes for workflows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Workflow


class WorkflowRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        name: str,
        code: str,
        workflow_type: str | None = None,
        indicator_types: list[str] | None = None,
        state: str = "draft",
        timeout_seconds: int = 300,
        retry_count: int = 0,
        is_active: bool = True,
        is_system: bool = False,
        tags: list[str] | None = None,
        time_saved_minutes: int | None = None,
        requires_approval: bool = True,
        approval_channel: str | None = None,
        approval_timeout_seconds: int = 3600,
        risk_level: str = "medium",
        documentation: str | None = None,
    ) -> Workflow:
        workflow = Workflow(
            uuid=uuid.uuid4(),
            name=name,
            workflow_type=workflow_type,
            indicator_types=indicator_types or [],
            code=code,
            code_version=1,
            state=state,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            is_active=is_active,
            is_system=is_system,
            tags=tags or [],
            time_saved_minutes=time_saved_minutes,
            requires_approval=requires_approval,
            approval_channel=approval_channel,
            approval_timeout_seconds=approval_timeout_seconds,
            risk_level=risk_level,
            documentation=documentation,
        )
        self._db.add(workflow)
        await self._db.flush()
        return workflow

    async def get_by_uuid(self, workflow_uuid: uuid.UUID) -> Workflow | None:
        result = await self._db.execute(
            select(Workflow).where(Workflow.uuid == workflow_uuid)
        )
        return result.scalar_one_or_none()

    async def get_by_name_and_system(self, name: str) -> Workflow | None:
        """Find a system workflow by name (used by seeders for idempotency)."""
        result = await self._db.execute(
            select(Workflow).where(Workflow.name == name, Workflow.is_system.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        *,
        workflow_type: str | None = None,
        state: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Workflow], int]:
        from sqlalchemy import func

        stmt = select(Workflow)
        count_stmt = select(func.count()).select_from(Workflow)

        if workflow_type is not None:
            stmt = stmt.where(Workflow.workflow_type == workflow_type)
            count_stmt = count_stmt.where(Workflow.workflow_type == workflow_type)
        if state is not None:
            stmt = stmt.where(Workflow.state == state)
            count_stmt = count_stmt.where(Workflow.state == state)
        if is_active is not None:
            stmt = stmt.where(Workflow.is_active == is_active)
            count_stmt = count_stmt.where(Workflow.is_active == is_active)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Workflow.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def patch(
        self,
        workflow: Workflow,
        *,
        name: str | None = None,
        workflow_type: str | None = None,
        indicator_types: list[str] | None = None,
        code: str | None = None,
        state: str | None = None,
        timeout_seconds: int | None = None,
        retry_count: int | None = None,
        is_active: bool | None = None,
        tags: list[str] | None = None,
        time_saved_minutes: int | None = None,
        requires_approval: bool | None = None,
        approval_channel: str | None = None,
        approval_timeout_seconds: int | None = None,
        risk_level: str | None = None,
        documentation: str | None = None,
    ) -> Workflow:
        if name is not None:
            workflow.name = name
        if workflow_type is not None:
            workflow.workflow_type = workflow_type
        if indicator_types is not None:
            workflow.indicator_types = indicator_types
        if code is not None:
            workflow.code = code
            workflow.code_version = workflow.code_version + 1
        if state is not None:
            workflow.state = state
        if timeout_seconds is not None:
            workflow.timeout_seconds = timeout_seconds
        if retry_count is not None:
            workflow.retry_count = retry_count
        if is_active is not None:
            workflow.is_active = is_active
        if tags is not None:
            workflow.tags = tags
        if time_saved_minutes is not None:
            workflow.time_saved_minutes = time_saved_minutes
        if requires_approval is not None:
            workflow.requires_approval = requires_approval
        if approval_channel is not None:
            workflow.approval_channel = approval_channel
        if approval_timeout_seconds is not None:
            workflow.approval_timeout_seconds = approval_timeout_seconds
        if risk_level is not None:
            workflow.risk_level = risk_level
        if documentation is not None:
            workflow.documentation = documentation
        await self._db.flush()
        return workflow

    async def upsert_system_workflow(self, **kwargs: Any) -> Workflow:
        """
        Insert or update a system workflow matched by name.
        Used by the builtin workflow seeder for idempotency.
        """
        name = kwargs["name"]
        existing = await self.get_by_name_and_system(name)
        if existing is not None:
            return existing
        return await self.create(is_system=True, **kwargs)

    async def delete(self, workflow: Workflow) -> None:
        await self._db.delete(workflow)
        await self._db.flush()
