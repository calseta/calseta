"""
Task queue factory.

Resolves the active backend from the QUEUE_BACKEND env var and returns
a `TaskQueueBase` instance. Fails fast on unknown values.

Valid values: "postgres" (default), "celery_redis", "sqs", "azure_service_bus"

All code outside this module imports `TaskQueueBase` only — never a
concrete backend class.
"""

from __future__ import annotations

from app.config import settings
from app.queue.base import TaskQueueBase

_VALID_BACKENDS = {"postgres", "celery_redis", "sqs", "azure_service_bus"}


def get_queue_backend() -> TaskQueueBase:
    """
    Instantiate and return the configured task queue backend.

    Raises:
        ValueError: If QUEUE_BACKEND is set to an unrecognised value.
    """
    backend_name = settings.QUEUE_BACKEND

    if backend_name not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown QUEUE_BACKEND={backend_name!r}. "
            f"Valid values: {sorted(_VALID_BACKENDS)}. "
            "See docs/architecture/QUEUE_BACKENDS.md for configuration instructions."
        )

    if backend_name == "postgres":
        from app.queue.backends.postgres import ProcrastinateBackend

        return ProcrastinateBackend(
            database_url=settings.DATABASE_URL,
            concurrency=settings.QUEUE_CONCURRENCY,
        )

    if backend_name == "celery_redis":
        from app.queue.backends.celery_redis import CeleryRedisBackend

        return CeleryRedisBackend()

    if backend_name == "sqs":
        from app.queue.backends.sqs import SQSBackend

        return SQSBackend()

    # azure_service_bus
    from app.queue.backends.azure_sb import AzureServiceBusBackend

    return AzureServiceBusBackend()
