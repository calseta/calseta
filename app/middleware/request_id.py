"""
RequestIDMiddleware — injects X-Request-ID into every request/response.

If the incoming request already carries X-Request-ID, that value is
preserved. Otherwise a new UUID4 is generated. The ID is bound to
structlog's context vars so all log lines within the request carry it
automatically — callers never pass request_id as a parameter.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Bind to structlog context so all log lines in this request carry it.
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
