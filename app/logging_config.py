"""
Structured logging configuration for all Calseta processes.

Call `configure_logging(service)` exactly once at process startup,
before any log calls are made. The `service` argument is bound globally
so every log line carries it without explicit passing.

Output modes (LOG_FORMAT env var):
    json   — newline-delimited JSON to stdout (production)
    text   — colored human-readable console output (development)

Every JSON log line includes:
    timestamp   ISO 8601 UTC
    level       DEBUG / INFO / WARNING / ERROR / CRITICAL
    service     api / worker / mcp
    version     APP_VERSION env var (default: dev)
    event       log message
    + any kwargs passed to the logger

HTTP request context:
    RequestIDMiddleware (app/middleware/request_id.py) binds `request_id`
    to structlog's contextvars. All log lines emitted within that request
    automatically include `request_id` — no explicit passing needed.

Worker task context:
    Task handlers bind `task_id` and `task_name` at task start via
    `structlog.contextvars.bind_contextvars(task_id=..., task_name=...)`.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings


def configure_logging(service: str) -> None:
    """
    Configure structlog and the standard library logging bridge.

    Args:
        service: Process identifier — "api", "worker", or "mcp".
                 Bound globally; included in every log line.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Processors shared by both renderers
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.LOG_FORMAT == "json":
        processors: list[structlog.types.Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
        renderer = processors[-1]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ]
        renderer = processors[-1]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bridge standard library logging into structlog so third-party libs
    # (SQLAlchemy, httpx, procrastinate) appear in the same output stream.
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[
            _StructlogHandler(renderer),  # type: ignore[arg-type]
        ],
        force=True,
    )

    # Bind global context fields to every log line
    structlog.contextvars.bind_contextvars(
        service=service,
        version=settings.APP_VERSION,
    )


class _StructlogHandler(logging.Handler):
    """
    Logging handler that routes stdlib log records into structlog.

    This lets third-party libraries that use `logging.getLogger()` appear
    in the same structured output stream as application code.
    """

    def __init__(self, renderer: structlog.types.Processor) -> None:
        super().__init__()
        self._renderer = renderer

    def emit(self, record: logging.LogRecord) -> None:
        # Build a minimal structlog event dict from the log record
        try:
            level = record.levelname.lower()
            logger = structlog.get_logger(record.name)
            log_fn = getattr(logger, level, logger.info)
            log_fn(
                record.getMessage(),
                exc_info=record.exc_info if record.exc_info else None,
            )
        except Exception:  # noqa: BLE001
            self.handleError(record)
