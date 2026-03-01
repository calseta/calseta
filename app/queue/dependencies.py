"""FastAPI dependency for the task queue singleton."""

from __future__ import annotations

from functools import lru_cache

from app.queue.base import TaskQueueBase
from app.queue.factory import get_queue_backend


@lru_cache(maxsize=1)
def _queue_singleton() -> TaskQueueBase:
    """Create the task queue backend once; reuse on every subsequent call."""
    return get_queue_backend()


def get_queue() -> TaskQueueBase:
    """
    FastAPI dependency — returns the shared task queue backend.

    Usage:
        @router.post("/items")
        async def create_item(
            queue: Annotated[TaskQueueBase, Depends(get_queue)],
        ) -> ...:
            await queue.enqueue("my_task", {...}, queue="default")
    """
    return _queue_singleton()
