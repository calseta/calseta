"""Base repository providing shared CRUD and pagination for all repositories."""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Generic repository with shared CRUD and pagination methods.

    Subclasses set the ``model`` class attribute to the SQLAlchemy model class
    and inherit ``get_by_id``, ``get_by_uuid``, ``count``, ``paginate``,
    ``delete``, and ``flush_and_refresh`` for free.

    Usage::

        class AlertRepository(BaseRepository[Alert]):
            model = Alert

            async def custom_query(self) -> list[Alert]:
                ...
    """

    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- Single-row lookups ---

    async def get_by_id(self, id: int) -> ModelT | None:  # noqa: A002
        """Fetch a single row by integer primary key."""
        result = await self._db.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_by_uuid(self, uuid: UUID) -> ModelT | None:
        """Fetch a single row by UUID column."""
        result = await self._db.execute(
            select(self.model).where(self.model.uuid == uuid)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    # --- Aggregate ---

    async def count(self, *filters: ColumnElement[bool]) -> int:
        """Return the count of rows matching the given filters."""
        stmt = select(func.count()).select_from(self.model)  # type: ignore[arg-type]
        for f in filters:
            stmt = stmt.where(f)
        result = await self._db.execute(stmt)
        return result.scalar_one()  # type: ignore[return-value]

    # --- Pagination ---

    async def paginate(
        self,
        *filters: ColumnElement[bool],
        order_by: Any = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ModelT], int]:
        """Return ``(rows, total_count)`` with offset-based pagination.

        Args:
            *filters: SQLAlchemy column expressions to filter by.
            order_by: A single SQLAlchemy order expression (e.g. ``Model.created_at.desc()``).
            page: 1-indexed page number.
            page_size: Number of rows per page.
        """
        # Count query
        count_stmt = select(func.count()).select_from(self.model)  # type: ignore[arg-type]
        for f in filters:
            count_stmt = count_stmt.where(f)
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()  # type: ignore[assignment]

        # Data query
        stmt = select(self.model)
        for f in filters:
            stmt = stmt.where(f)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    # --- Mutation helpers ---

    async def delete(self, obj: ModelT) -> None:
        """Delete a row and flush the session."""
        await self._db.delete(obj)
        await self._db.flush()

    async def flush_and_refresh(self, obj: ModelT) -> ModelT:
        """Flush pending changes and refresh the object from the database."""
        await self._db.flush()
        await self._db.refresh(obj)
        return obj
