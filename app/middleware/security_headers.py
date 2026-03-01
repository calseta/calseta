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

_COMMON_HEADERS: list[tuple[str, str]] = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-XSS-Protection", "1; mode=block"),
    ("Referrer-Policy", "no-referrer"),
    (
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=()",
    ),
]

# Strict CSP for API routes — blocks all browser resource loading.
_API_CSP = "default-src 'none'"

# Permissive CSP for the admin UI — allows same-origin scripts/styles
# and external font loading from Google Fonts.
_UI_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'"
)

_API_PREFIXES = ("/v1/", "/health", "/docs", "/redoc", "/openapi.json")

_HSTS_VALUE = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _COMMON_HEADERS:
            response.headers[header] = value

        # Use strict CSP for API routes, permissive CSP for the admin UI.
        is_api = any(request.url.path.startswith(p) for p in _API_PREFIXES)
        response.headers["Content-Security-Policy"] = (
            _API_CSP if is_api else _UI_CSP
        )

        if settings.HTTPS_ENABLED and settings.SECURITY_HEADER_HSTS_ENABLED:
            response.headers["Strict-Transport-Security"] = _HSTS_VALUE
        return response
