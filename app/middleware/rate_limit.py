"""
Rate limiter setup using slowapi.

Usage in route handlers:
    from app.middleware.rate_limit import limiter

    @limiter.limit(f"{settings.RATE_LIMIT_INGEST_PER_MINUTE}/minute")
    @router.post("/ingest/sentinel")
    async def ingest_sentinel(request: Request, ...) -> ...:
        ...  # request: Request MUST be the first parameter for slowapi

The `limiter` object is also set on `app.state.limiter` in create_app().
A RateLimitExceeded exception handler is registered there too.

Key function:
    - Authenticated requests → keyed by `key_prefix` from request.state.auth
    - Unauthenticated requests → keyed by real client IP

X-Forwarded-For trusted hops are controlled by TRUSTED_PROXY_COUNT.

Default limit strings (used as router-level defaults on rate-limited routes):
    RATE_LIMIT_AUTHED_PER_MINUTE   — standard authenticated endpoints
    RATE_LIMIT_INGEST_PER_MINUTE   — ingest routes (tighter)
    RATE_LIMIT_ENRICHMENT_PER_MINUTE — on-demand enrichment routes
    RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE — workflow execute routes
"""

from __future__ import annotations

from starlette.requests import Request

from app.config import settings


def _extract_client_ip(request: Request) -> str:
    """
    Return the real client IP, respecting TRUSTED_PROXY_COUNT.

    When TRUSTED_PROXY_COUNT > 0, reads X-Forwarded-For and takes the IP
    that is TRUSTED_PROXY_COUNT hops from the right end of the list.
    """
    if settings.TRUSTED_PROXY_COUNT > 0:
        xff = request.headers.get("X-Forwarded-For", "")
        ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
        if ips:
            # Real client is TRUSTED_PROXY_COUNT hops from the right
            idx = max(0, len(ips) - settings.TRUSTED_PROXY_COUNT - 1)
            return ips[idx]

    if request.client:
        return request.client.host
    return "unknown"


def get_rate_limit_key(request: Request) -> str:
    """
    slowapi key function.

    Returns a string that uniquely identifies the rate limit bucket:
    - Authenticated requests: "key:<key_prefix>"
    - Unauthenticated requests: "ip:<real_ip>"
    """
    auth = getattr(request.state, "auth", None)
    if auth is not None:
        return f"key:{auth.key_prefix}"
    return f"ip:{_extract_client_ip(request)}"


# ---------------------------------------------------------------------------
# Limiter singleton — imported by routes and registered on app.state
# ---------------------------------------------------------------------------

from slowapi import Limiter  # noqa: E402

limiter = Limiter(key_func=get_rate_limit_key)
