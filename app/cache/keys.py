"""Cache key construction for enrichment results."""

from __future__ import annotations


def make_enrichment_key(provider_name: str, indicator_type: str, value: str) -> str:
    """
    Build the cache key for an enrichment result.

    Format: `enrichment:{provider}:{type}:{value}`

    Args:
        provider_name:   Provider identifier (e.g. "virustotal").
        indicator_type:  Indicator type string (e.g. "ip", "domain").
        value:           The indicator value (e.g. "1.2.3.4").

    Returns:
        A deterministic string key safe for use as a dict key or Redis key.
    """
    return f"enrichment:{provider_name}:{indicator_type}:{value}"
