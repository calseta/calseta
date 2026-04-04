"""Sync provider registry — maps provider_type strings to SyncProviderBase instances."""
from __future__ import annotations

from app.integrations.kb_sync.base import SyncProviderBase
from app.integrations.kb_sync.confluence_sync import ConfluenceSyncProvider
from app.integrations.kb_sync.github_sync import GitHubSyncProvider
from app.integrations.kb_sync.url_sync import URLSyncProvider

_REGISTRY: dict[str, SyncProviderBase] = {
    "github": GitHubSyncProvider(),
    "github_wiki": GitHubSyncProvider(),  # same provider; callers use "github_wiki" type
    "confluence": ConfluenceSyncProvider(),
    "url": URLSyncProvider(),
}


def get_sync_provider(provider_type: str) -> SyncProviderBase | None:
    """Return the SyncProviderBase for the given type string, or None if unknown."""
    return _REGISTRY.get(provider_type)


def list_provider_types() -> list[str]:
    """Return the list of registered provider type strings."""
    return list(_REGISTRY.keys())
