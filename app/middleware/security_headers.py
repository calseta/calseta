"""
SecurityHeadersMiddleware — adds security headers to every response.

Headers added (per PRD Section 7.13):
    X-Content-Type-Options: nosniff                 — always
    X-Frame-Options: DENY                           — always
    X-XSS-Protection: 1; mode=block                — always
    Referrer-Policy: no-referrer                    — always
    Content-Security-Policy: default-src 'none'    — always
    Permissions-Policy: geolocation=(), ...         — always
    Strict-Transport-Security: max-age=63072000...  — only when HTTPS_ENABLED=true

Individual headers can be disabled via settings flags (e.g.,
SECURITY_HEADER_HSTS_ENABLED=false) for dev/non-HTTPS environments.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

_STATIC_HEADERS: list[tuple[str, str]] = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-XSS-Protection", "1; mode=block"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", "default-src 'none'"),
    (
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=()",
    ),
]

_HSTS_VALUE = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_HEADERS:
            response.headers[header] = value
        if settings.HTTPS_ENABLED and settings.SECURITY_HEADER_HSTS_ENABLED:
            response.headers["Strict-Transport-Security"] = _HSTS_VALUE
        return response
