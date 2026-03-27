"""Shared session management for task handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """Open an async DB session for a task handler.

    Commits on success, rolls back on exception. The ``AsyncSessionLocal``
    import is deferred to match the existing pattern in ``registry.py``
    where heavy imports happen inside the task function body.
    """
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
