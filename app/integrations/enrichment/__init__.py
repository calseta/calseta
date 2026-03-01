"""
Enrichment provider package — registers all built-in providers.

Import order matters: registry must be imported before providers are registered.
"""

from app.integrations.enrichment.abuseipdb import AbuseIPDBProvider
from app.integrations.enrichment.entra import EntraProvider
from app.integrations.enrichment.okta import OktaProvider
from app.integrations.enrichment.registry import enrichment_registry
from app.integrations.enrichment.virustotal import VirusTotalProvider

enrichment_registry.register(VirusTotalProvider())
enrichment_registry.register(AbuseIPDBProvider())
enrichment_registry.register(OktaProvider())
enrichment_registry.register(EntraProvider())
