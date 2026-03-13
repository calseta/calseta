"""
BodySizeLimitMiddleware — rejects requests exceeding the configured size.

Limits (from settings):
    MAX_INGEST_PAYLOAD_SIZE_MB  — applies to POST /v1/ingest/* and POST /v1/alerts
    MAX_REQUEST_BODY_SIZE_MB    — applies to all other endpoints

Fast path: check Content-Length header and reject immediately.
Chunked transfers (no Content-Length) pass through unchecked — the
application layer enforces limits when reading the body.

Returns 413 PAYLOAD_TOO_LARGE using the standard ErrorResponse format.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_413_CONTENT_TOO_LARGE

from app.config import settings
from app.schemas.common import ErrorDetail, ErrorResponse

_INGEST_PATHS = {"/v1/alerts"}
_INGEST_PREFIX = "/v1/ingest/"


def _is_ingest_endpoint(path: str) -> bool:
    return path.startswith(_INGEST_PREFIX) or path in _INGEST_PATHS


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length_header = request.headers.get("content-length")
        if content_length_header is None:
            return await call_next(request)

        try:
            content_length = int(content_length_header)
        except ValueError:
            return await call_next(request)

        if _is_ingest_endpoint(request.url.path):
            max_bytes = settings.MAX_INGEST_PAYLOAD_SIZE_MB * 1024 * 1024
            limit_label = f"{settings.MAX_INGEST_PAYLOAD_SIZE_MB}MB"
            scope = "ingest endpoints"
        else:
            max_bytes = settings.MAX_REQUEST_BODY_SIZE_MB * 1024 * 1024
            limit_label = f"{settings.MAX_REQUEST_BODY_SIZE_MB}MB"
            scope = "this endpoint"

        if content_length > max_bytes:
            body = ErrorResponse(
                error=ErrorDetail(
                    code="PAYLOAD_TOO_LARGE",
                    message=(
                        f"Request body exceeds the {limit_label} limit for "
                        f"{scope}."
                    ),
                    details={},
                )
            ).model_dump()
            return JSONResponse(
                status_code=HTTP_413_CONTENT_TOO_LARGE, content=body
            )

        return await call_next(request)
