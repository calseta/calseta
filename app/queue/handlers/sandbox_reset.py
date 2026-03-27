"""Handler for the sandbox_reset periodic task."""

from __future__ import annotations

import structlog

from app.queue.handlers.payloads import SandboxResetPayload
from app.tasks.sandbox_reset import reset_sandbox

logger = structlog.get_logger()


class SandboxResetHandler:
    """Reset the sandbox database daily at midnight UTC.

    Deletes transient data, user-created config, and re-seeds fixtures.
    Only registered when SANDBOX_MODE=true.
    """

    async def execute(self, payload: SandboxResetPayload) -> None:
        logger.info("sandbox_reset_task_triggered", timestamp=payload.timestamp)
        counts = await reset_sandbox()
        logger.info("sandbox_reset_task_complete", deleted_counts=counts)
