"""
Enrichment provider package — registers all built-in providers.

Import order matters: registry must be imported before providers are registered.

When ENRICHMENT_MOCK_MODE is enabled, mock providers are registered instead of
real providers. Mock providers share the same provider_name as their real
counterparts so the rest of the pipeline (enrichment service, registry, API)
works identically.
"""

from app.config import settings
from app.integrations.enrichment.registry import enrichment_registry

if settings.ENRICHMENT_MOCK_MODE:
    from app.integrations.enrichment.mocks.abuseipdb_mock import MockAbuseIPDBProvider
    from app.integrations.enrichment.mocks.entra_mock import MockEntraProvider
    from app.integrations.enrichment.mocks.okta_mock import MockOktaProvider
    from app.integrations.enrichment.mocks.virustotal_mock import MockVirusTotalProvider

    enrichment_registry.register(MockVirusTotalProvider())
    enrichment_registry.register(MockAbuseIPDBProvider())
    enrichment_registry.register(MockOktaProvider())
    enrichment_registry.register(MockEntraProvider())
else:
    from app.integrations.enrichment.abuseipdb import AbuseIPDBProvider
    from app.integrations.enrichment.entra import EntraProvider
    from app.integrations.enrichment.okta import OktaProvider
    from app.integrations.enrichment.virustotal import VirusTotalProvider

    enrichment_registry.register(VirusTotalProvider())
    enrichment_registry.register(AbuseIPDBProvider())
    enrichment_registry.register(OktaProvider())
    enrichment_registry.register(EntraProvider())
