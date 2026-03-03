"""
Enrichment provider package.

Providers are now loaded from the database at startup via
``enrichment_registry.load_from_database()``, called from ``app/main.py``.

The legacy code-based providers (virustotal.py, abuseipdb.py, okta.py, entra.py)
are kept as reference but no longer imported or registered here.
"""

from app.integrations.enrichment.registry import enrichment_registry

__all__ = ["enrichment_registry"]
