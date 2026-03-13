"""
InMemoryCache — in-process dict-based cache with per-entry TTL expiry.

Suitable for single-process deployments (API server or worker).
For multi-process setups (separate API + worker containers), each process
has its own cache — this is acceptable for v1 since enrichment only runs
in the worker process.

Thread-safe for asyncio: Python's GIL ensures dict reads/writes are atomic.
No asyncio locks needed for a single-threaded event loop.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.cache.base import CacheBackendBase

logger = structlog.get_logger(__name__)


class InMemoryCache(CacheBackendBase):
    """
    In-memory cache with dict + expiry timestamp per entry.

    Entry format: {key: (value, expires_at_monotonic)}
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Any | None:
        """Return value if present and not expired. Returns None otherwise."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store value with TTL. Overwrites any existing entry."""
        expires_at = time.monotonic() + ttl_seconds
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        """Remove entry. No-op if absent."""
        self._store.pop(key, None)

    def evict_expired(self) -> int:
        """
        Remove all expired entries. Returns the count evicted.

        Call periodically to reclaim memory. Not called automatically —
        callers use this for housekeeping, typically in a background task.
        """
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        """Current number of entries (including possibly-expired ones)."""
        return len(self._store)
