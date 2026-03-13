"""
Cache backend factory.

Resolves from CACHE_BACKEND env var. Only 'memory' is supported in v1.
Future: 'redis' backend (see docs/CACHE_BACKENDS.md).
"""

from __future__ import annotations

from functools import lru_cache

from app.cache.base import CacheBackendBase


@lru_cache(maxsize=1)
def get_cache_backend() -> CacheBackendBase:
    """
    Return the configured cache backend singleton.

    Raises ValueError for unknown CACHE_BACKEND values.
    """
    from app.config import settings

    backend_name = getattr(settings, "CACHE_BACKEND", "memory")

    if backend_name == "memory":
        from app.cache.memory import InMemoryCache

        return InMemoryCache()

    raise ValueError(
        f"Unknown CACHE_BACKEND={backend_name!r}. "
        "Valid values: 'memory'. See docs/CACHE_BACKENDS.md."
    )
