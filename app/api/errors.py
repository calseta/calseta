"""
Global exception types and FastAPI exception handlers.

All errors returned by the API use ErrorResponse format:
    {"error": {"code": "...", "message": "...", "details": {}}}

Register the handlers on the FastAPI app via register_exception_handlers().
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorDetail, ErrorResponse


class CalsetaException(Exception):
    """
    Base exception for all application-level errors.
    Raised by services and route handlers; caught by the global handler.
    Never raise HTTPException directly — use CalsetaException instead.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _error_body(
    code: str, message: str, details: dict[str, object] | None = None
) -> dict[str, object]:
    return ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or {})
    ).model_dump()


async def calseta_exception_handler(
    _request: Request, exc: CalsetaException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, exc.details),
    )


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "VALIDATION_ERROR",
            "Request validation failed.",
            {"errors": exc.errors()},
        ),
    )


async def not_found_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=_error_body("NOT_FOUND", "The requested resource was not found."),
    )


async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("INTERNAL_ERROR", "An unexpected error occurred."),
    )


def register_exception_handlers(app: object) -> None:
    """Register all global exception handlers on the FastAPI app."""
    from fastapi import FastAPI
    from starlette.exceptions import HTTPException as StarletteHTTPException

    assert isinstance(app, FastAPI)
    app.add_exception_handler(CalsetaException, calseta_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)  # type: ignore[arg-type]
