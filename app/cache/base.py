"""
CacheBackendBase — abstract interface for the enrichment result cache.

Only one backend in v1: InMemoryCache.
The interface is designed for a future Redis backend — never import a concrete
implementation directly from services or routes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CacheBackendBase(ABC):
    """Abstract cache backend. Key/value store with per-entry TTL."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """
        Return cached value for key, or None if absent or expired.

        Never raises — returns None on any error.
        """

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """
        Store value under key with TTL.

        After ttl_seconds, the entry is treated as absent.
        Never raises — logs and continues on any error.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove an entry. No-op if key does not exist."""
