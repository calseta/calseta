"""
TaskQueueBase — abstract interface for the Calseta task queue.

All async work (enrichment, dispatch, workflow execution) is enqueued
through this interface. Route handlers and services import ONLY this
module — never a concrete backend. This keeps the backend swappable and
tests fast (mock the interface).

All task handlers registered in app/queue/registry.py must be idempotent
— safe to execute more than once.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class QueueMetricsEntry:
    """Metrics for a single named queue."""

    queue: str
    pending: int = 0
    in_progress: int = 0
    succeeded_30d: int = 0
    failed_30d: int = 0
    avg_duration_seconds: float | None = None
    oldest_pending_age_seconds: float | None = None


@dataclass
class QueueMetrics:
    """Aggregated queue health metrics."""

    queues: list[QueueMetricsEntry] = field(default_factory=list)
    total_pending: int = 0
    total_in_progress: int = 0
    total_failed_30d: int = 0
    total_succeeded_30d: int = 0
    oldest_pending_age_seconds: float | None = None


class TaskQueueBase(ABC):
    """
    Abstract task queue interface.

    Implementations:
        - ProcrastinateBackend (default, postgres)
        - CeleryRedisBackend   (stub — see docs/architecture/QUEUE_BACKENDS.md)
        - SQSBackend           (stub — see docs/architecture/QUEUE_BACKENDS.md)
        - AzureServiceBusBackend (stub — see docs/architecture/QUEUE_BACKENDS.md)

    Selected via QUEUE_BACKEND env var in app/queue/factory.py.
    """

    @abstractmethod
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
        Enqueue a named task with the given payload.

        Returns a string task ID. The task must be registered in
        app/queue/registry.py before it can be enqueued.

        Args:
            task_name:     Registered task function name (e.g. "enrich_alert")
            payload:       Keyword arguments passed to the task function
            queue:         Named queue: "enrichment", "dispatch", "workflows", "default"
            delay_seconds: Delay execution by this many seconds (0 = immediate)
            priority:      Higher values run first (backend support varies)
        """

    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Return the current status of a previously enqueued task."""

    @abstractmethod
    async def get_queue_metrics(self) -> QueueMetrics:
        """Return health metrics for all known queues."""

    @abstractmethod
    async def start_worker(self, queues: list[str]) -> None:
        """
        Start consuming tasks from the given queues.

        Blocks until the worker exits (call from the worker process entry point).
        Must handle SIGTERM gracefully, finishing the current job and exiting
        within a reasonable timeout.
        """
