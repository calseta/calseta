"""
Auth failure audit logging.

All authentication failures are logged through this single function.
It emits a structured JSON event to stdout via structlog, which the
deployment layer routes to CloudWatch, Datadog, Azure Monitor, etc.

Never call logger.warning("auth_failure", ...) directly — always use
log_auth_failure() so the log format stays consistent and testable.
"""

from __future__ import annotations

import structlog
from starlette.requests import Request

logger = structlog.get_logger(__name__)


def log_auth_failure(
    reason: str,
    request: Request,
    key_prefix: str | None = None,
    required_scope: str | None = None,
) -> None:
    """
    Emit a structured auth_failure event.

    Args:
        reason:         Short machine-readable reason code. Values:
                        "missing_header", "invalid_format", "invalid_key",
                        "key_expired", "insufficient_scope", "invalid_signature"
        request:        The incoming HTTP request (for method, path, client IP)
        key_prefix:     First 8 chars of the presented key (if parseable)
        required_scope: The scope that was required but not held (for 403s)
    """
    logger.warning(
        "auth_failure",
        reason=reason,
        method=request.method,
        path=request.url.path,
        key_prefix=key_prefix,
        required_scope=required_scope,
    )
