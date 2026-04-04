"""AgentTool repository — all DB reads/writes for the agent_tools table.

Note: AgentTool uses a text primary key (tool id string), not a serial integer.
It does not inherit from BaseRepository due to the non-standard PK type.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_tool import AgentTool
from app.schemas.agent_tools import AgentToolCreate


class AgentToolRepository:
    """Repository for agent tool registry operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, tool_id: str) -> AgentTool | None:
        """Fetch a single tool by its text id."""
        result = await self._db.execute(
            select(AgentTool).where(AgentTool.id == tool_id)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_all(
        self,
        tier: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentTool], int]:
        """Return (tools, total_count) with optional tier/category filters."""
        stmt = select(AgentTool)
        count_stmt = select(func.count()).select_from(AgentTool)

        if tier is not None:
            stmt = stmt.where(AgentTool.tier == tier)
            count_stmt = count_stmt.where(AgentTool.tier == tier)
        if category is not None:
            stmt = stmt.where(AgentTool.category == category)
            count_stmt = count_stmt.where(AgentTool.category == category)

        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(AgentTool.id.asc()).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, data: AgentToolCreate) -> AgentTool:
        """Insert a new tool. Raises if id already exists."""
        tool = AgentTool(
            id=data.id,
            display_name=data.display_name,
            description=data.description,
            documentation=data.documentation,
            tier=data.tier.value,
            category=data.category.value,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            handler_ref=data.handler_ref,
            is_active=True,
        )
        self._db.add(tool)
        await self._db.flush()
        await self._db.refresh(tool)
        return tool

    async def patch(self, tool: AgentTool, **kwargs: Any) -> AgentTool:
        """Apply partial updates to a tool."""
        _UPDATABLE = frozenset(
            {"display_name", "description", "documentation", "tier", "is_active"}
        )
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable via patch")
            setattr(tool, key, value)
        await self._db.flush()
        await self._db.refresh(tool)
        return tool

    async def delete(self, tool: AgentTool) -> None:
        """Delete a tool and flush the session."""
        await self._db.delete(tool)
        await self._db.flush()

    async def get_by_ids(self, tool_ids: list[str]) -> list[AgentTool]:
        """Fetch multiple tools by id list. Preserves no particular order."""
        if not tool_ids:
            return []
        result = await self._db.execute(
            select(AgentTool).where(AgentTool.id.in_(tool_ids))
        )
        return list(result.scalars().all())

    async def upsert(self, data: AgentToolCreate) -> AgentTool:
        """Insert or update a tool — used for auto-registration of built-ins.

        On conflict (same id): updates all mutable fields.
        Returns the ORM object (refreshed from DB).
        """
        stmt = (
            pg_insert(AgentTool)
            .values(
                id=data.id,
                display_name=data.display_name,
                description=data.description,
                documentation=data.documentation,
                tier=data.tier.value,
                category=data.category.value,
                input_schema=data.input_schema,
                output_schema=data.output_schema,
                handler_ref=data.handler_ref,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "display_name": data.display_name,
                    "description": data.description,
                    "documentation": data.documentation,
                    "tier": data.tier.value,
                    "category": data.category.value,
                    "input_schema": data.input_schema,
                    "output_schema": data.output_schema,
                    "handler_ref": data.handler_ref,
                },
            )
        )
        await self._db.execute(stmt)
        await self._db.flush()

        tool = await self.get_by_id(data.id)
        assert tool is not None  # just inserted
        await self._db.refresh(tool)
        return tool
