"""Base class for KB sync providers."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class SyncResult:
    outcome: str  # 'updated' | 'no_change' | 'fetch_failed' | 'config_invalid'
    content: str | None = None      # new content if outcome='updated'
    content_hash: str | None = None  # hash of new content
    error_message: str | None = None
    sync_source_ref: str | None = None  # commit SHA, confluence version ID, etc.


class SyncProviderBase(ABC):
    provider_type: str  # 'github' | 'github_wiki' | 'confluence' | 'url'

    @abstractmethod
    async def fetch(
        self,
        sync_config: dict,
        secret_resolver: object | None = None,
    ) -> SyncResult:
        """Fetch content from external source. Must never raise — return fetch_failed on error."""
        ...

    def validate_config(self, sync_config: dict) -> list[str]:
        """Return list of validation errors. Empty = valid."""
        return []


# ---------------------------------------------------------------------------
# Shared helpers used by all sync providers
# ---------------------------------------------------------------------------


def _sha256(content: str) -> str:
    """Return the SHA-256 hex digest of the given string (UTF-8 encoded)."""
    return hashlib.sha256(content.encode()).hexdigest()


async def _resolve_token(sync_config: dict, secret_resolver: object | None) -> str | None:
    """Resolve an auth token from sync_config.

    Supports:
      - {"auth": {"type": "secret_ref", "secret_name": "my_secret"}}  — delegates to resolver
      - {"auth": {"type": "bearer", "token": "raw_token"}}             — uses literal value
    Returns None if no auth is configured or resolution fails.
    """
    auth = sync_config.get("auth")
    if not auth:
        return None
    if auth.get("type") == "secret_ref" and secret_resolver is not None:
        try:
            result = await secret_resolver.resolve(auth.get("secret_name", ""))  # type: ignore[attr-defined]
            return str(result) if result is not None else None
        except Exception:
            return None
    if auth.get("type") == "bearer":
        return str(auth["token"]) if auth.get("token") else None
    return None
