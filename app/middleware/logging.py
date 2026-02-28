"""
RequestLoggingMiddleware — emits one structured log line per request.

Log fields:
    method       HTTP method
    path         request path (no query string — avoids logging sensitive params)
    status_code  response status
    duration_ms  wall-clock time in milliseconds (float, 2 decimal places)

The request_id is already bound to structlog's context vars by
RequestIDMiddleware (which must be added to the app first), so it
appears in this log line automatically.
"""

from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
