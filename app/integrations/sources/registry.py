"""
Source plugin registry — singleton that maps source_name → AlertSourceBase instance.

All built-in sources are registered at import time in __init__.py.
The registry is queried by the ingest endpoint to look up the correct plugin.
"""

from __future__ import annotations

from app.integrations.sources.base import AlertSourceBase


class SourceRegistry:
    """Singleton registry mapping source_name → AlertSourceBase instance."""

    def __init__(self) -> None:
        self._sources: dict[str, AlertSourceBase] = {}

    def register(self, source: AlertSourceBase) -> None:
        """
        Register a source plugin.

        Raises ValueError if a source with the same source_name is already registered.
        """
        if source.source_name in self._sources:
            raise ValueError(
                f"Source '{source.source_name}' is already registered. "
                "Each source_name must be unique."
            )
        self._sources[source.source_name] = source

    def get(self, source_name: str) -> AlertSourceBase | None:
        """Return the source plugin for the given name, or None if not registered."""
        return self._sources.get(source_name)

    def list_all(self) -> list[AlertSourceBase]:
        """Return all registered source plugins."""
        return list(self._sources.values())


# Module-level singleton — imported by ingest routes and tests.
source_registry = SourceRegistry()
