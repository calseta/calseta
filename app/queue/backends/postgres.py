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

from app.queue.base import QueueMetrics, QueueMetricsEntry, TaskQueueBase, TaskStatus

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
        # Reuse the shared App from registry — tasks are already registered on it.
        # Creating a separate App instance here would mean those tasks are invisible
        # to this backend when enqueue() looks them up via app.tasks.get(name).
        from app.queue.registry import procrastinate_app

        self.app = procrastinate_app

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

    async def get_queue_metrics(self) -> QueueMetrics:
        """Query procrastinate_jobs for per-queue health metrics."""
        from datetime import UTC, datetime, timedelta

        import psycopg

        now = datetime.now(UTC)
        thirty_days_ago = now - timedelta(days=30)

        async with (
            await psycopg.AsyncConnection.connect(self._pg_dsn) as conn,
            conn.cursor() as cur,
        ):
            await cur.execute(
                """
                SELECT
                    queue_name,
                    COUNT(*) FILTER (WHERE status = 'todo') AS pending,
                    COUNT(*) FILTER (WHERE status = 'doing') AS in_progress,
                    COUNT(*) FILTER (
                        WHERE status = 'succeeded' AND finished_at >= %(since)s
                    ) AS succeeded_30d,
                    COUNT(*) FILTER (
                        WHERE status = 'failed' AND finished_at >= %(since)s
                    ) AS failed_30d,
                    AVG(EXTRACT(EPOCH FROM finished_at - started_at))
                        FILTER (
                            WHERE status = 'succeeded' AND finished_at >= %(since)s
                        ) AS avg_duration,
                    MAX(EXTRACT(EPOCH FROM %(now)s - scheduled_at))
                        FILTER (WHERE status = 'todo') AS oldest_pending_age
                FROM procrastinate_jobs
                GROUP BY queue_name
                """,
                {"since": thirty_days_ago, "now": now},
            )
            rows = await cur.fetchall()

        entries: list[QueueMetricsEntry] = []
        total_pending = 0
        total_in_progress = 0
        total_failed = 0
        total_succeeded = 0
        max_oldest: float | None = None

        for row in rows:
            entry = QueueMetricsEntry(
                queue=row[0],
                pending=row[1] or 0,
                in_progress=row[2] or 0,
                succeeded_30d=row[3] or 0,
                failed_30d=row[4] or 0,
                avg_duration_seconds=float(row[5]) if row[5] is not None else None,
                oldest_pending_age_seconds=(
                    float(row[6]) if row[6] is not None else None
                ),
            )
            entries.append(entry)
            total_pending += entry.pending
            total_in_progress += entry.in_progress
            total_failed += entry.failed_30d
            total_succeeded += entry.succeeded_30d
            if entry.oldest_pending_age_seconds is not None:
                if max_oldest is None or entry.oldest_pending_age_seconds > max_oldest:
                    max_oldest = entry.oldest_pending_age_seconds

        return QueueMetrics(
            queues=entries,
            total_pending=total_pending,
            total_in_progress=total_in_progress,
            total_failed_30d=total_failed,
            total_succeeded_30d=total_succeeded,
            oldest_pending_age_seconds=max_oldest,
        )

    async def start_worker(self, queues: list[str]) -> None:
        """
        Block and consume tasks from the named queues.

        Called from worker.py main loop. The app must be opened first to
        initialize the psycopg connection pool. SIGTERM causes graceful
        shutdown (procrastinate finishes the current job then exits).
        """
        async with self.app.open_async():
            await self.app.run_worker_async(
                queues=queues,
                concurrency=self._concurrency,
            )
