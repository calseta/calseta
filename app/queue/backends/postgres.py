"""
ProcrastinateBackend — procrastinate + PostgreSQL task queue.

This is the default and recommended backend. Tasks are stored durably in
PostgreSQL using procrastinate's `procrastinate_jobs` table, which is
created by Alembic migration (procrastinate ships its own schema).

Driver note:
    procrastinate v3 removed AsyncpgConnector. It now uses PsycopgConnector
    (psycopg3 / psycopg_pool). Both `asyncpg` (for SQLAlchemy) and `psycopg`
    (for procrastinate) connect to the same PostgreSQL instance. This is
    intentional — they are independent driver choices for each library.

    DATABASE_URL is in SQLAlchemy format: postgresql+asyncpg://...
    PsycopgConnector expects standard libpq DSN: postgresql://...
    The `+asyncpg` specifier is stripped at construction time.

Enqueue performance:
    Each enqueue() call opens a fresh pool and closes it. For high-volume
    deployments, wire open_async() into FastAPI lifespan to reuse the pool.
    Deferred to Wave 5+ since enqueueing isn't called in Wave 1.

SIGTERM handling:
    procrastinate's run_worker_async() handles SIGTERM natively — it
    finishes the current job, then exits cleanly.
"""

from __future__ import annotations

import procrastinate

from app.queue.base import TaskQueueBase, TaskStatus

# Procrastinate job status → TaskStatus mapping
_STATUS_MAP: dict[str, TaskStatus] = {
    "todo": TaskStatus.PENDING,
    "doing": TaskStatus.IN_PROGRESS,
    "succeeded": TaskStatus.SUCCESS,
    "failed": TaskStatus.FAILED,
}


def _to_pg_dsn(database_url: str) -> str:
    """
    Convert SQLAlchemy DSN format to plain libpq DSN.

    postgresql+asyncpg://user:pass@host/db  →  postgresql://user:pass@host/db
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


class ProcrastinateBackend(TaskQueueBase):
    def __init__(self, database_url: str, concurrency: int = 10) -> None:
        self._pg_dsn = _to_pg_dsn(database_url)
        self._concurrency = concurrency
        self._connector = procrastinate.PsycopgConnector(conninfo=self._pg_dsn)
        self.app = procrastinate.App(connector=self._connector)

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, object],
        *,
        queue: str,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> str:
        """
        Enqueue a registered procrastinate task by name.

        The task must be decorated with @backend.app.task and registered
        in app/queue/registry.py, which is imported by the worker and the
        API startup event.
        """
        task = self.app.tasks.get(task_name)
        if task is None:
            raise ValueError(
                f"Task {task_name!r} is not registered. "
                "Ensure app/queue/registry.py is imported at startup."
            )

        defer_kwargs: dict[str, object] = dict(payload)
        if delay_seconds > 0:
            defer_kwargs["schedule_in"] = {"seconds": delay_seconds}

        async with self.app.open_async():
            job_id: int = await task.defer_async(**defer_kwargs)

        return str(job_id)

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Query procrastinate_jobs to get the current job status."""
        import psycopg

        job_pk = int(task_id)
        async with (
            await psycopg.AsyncConnection.connect(self._pg_dsn) as conn,
            conn.cursor() as cur,
        ):
            await cur.execute(
                "SELECT status FROM procrastinate_jobs WHERE id = %s",
                (job_pk,),
            )
            row = await cur.fetchone()

        if row is None:
            return TaskStatus.FAILED  # Not found — treat as unknown/failed

        raw_status: str = row[0]
        return _STATUS_MAP.get(raw_status, TaskStatus.FAILED)

    async def start_worker(self, queues: list[str]) -> None:
        """
        Block and consume tasks from the named queues.

        Called from worker.py main loop. SIGTERM causes graceful shutdown
        (procrastinate finishes the current job then exits).
        """
        await self.app.run_worker_async(
            queues=queues,
            concurrency=self._concurrency,
        )
