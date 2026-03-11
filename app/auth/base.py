"""
AuthBackendBase — abstract interface for authentication backends.

Route files import only `AuthBackendBase` and `AuthContext` — never
any concrete backend (e.g. `APIKeyAuthBackend`). This keeps the auth
mechanism swappable without touching route code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from starlette.requests import Request


@dataclass
class AuthContext:
    """
    Populated by `AuthBackendBase.authenticate()` on every successful request.

    Attributes:
        key_prefix  First 8 chars of the API key — used for rate limit keying,
                    audit logging, and display. Never the full key or hash.
        scopes      Granted scopes for this key (e.g. ["alerts:read", "admin"]).
        key_id      Internal DB row id — used for background `last_used_at` updates.
    """

    key_prefix: str
    scopes: list[str]
    key_id: int
    key_type: str = field(default="human")
    allowed_sources: list[str] | None = field(default=None)


class AuthBackendBase(ABC):
    """
    Abstract authentication backend.

    Implementors raise `CalsetaException` (code="UNAUTHORIZED", status=401)
    on any authentication failure. Never raise `HTTPException` directly.
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> AuthContext:
        """
        Extract and validate credentials from the request.

        Returns AuthContext on success.
        Raises CalsetaException(code="UNAUTHORIZED", status_code=401) on failure.
        """
