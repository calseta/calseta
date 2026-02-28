"""
CeleryRedisBackend — stub.

Not implemented. See docs/QUEUE_BACKENDS.md for switching instructions.
"""

from __future__ import annotations

from app.queue.base import TaskQueueBase, TaskStatus


class CeleryRedisBackend(TaskQueueBase):
    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, object],
        *,
        queue: str,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> str:
        raise NotImplementedError(
            "Set QUEUE_BACKEND=postgres or see docs/QUEUE_BACKENDS.md"
        )

    async def get_task_status(self, task_id: str) -> TaskStatus:
        raise NotImplementedError(
            "Set QUEUE_BACKEND=postgres or see docs/QUEUE_BACKENDS.md"
        )

    async def start_worker(self, queues: list[str]) -> None:
        raise NotImplementedError(
            "Set QUEUE_BACKEND=postgres or see docs/QUEUE_BACKENDS.md"
        )
