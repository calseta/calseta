"""
Alert source plugin package.

All built-in sources are imported and registered here at package import time.
The ingest endpoint imports source_registry from this package.

Adding a new source:
    1. Create app/integrations/sources/{name}.py with MySource(AlertSourceBase)
    2. Add: from app.integrations.sources.{name} import MySource
    3. Add: source_registry.register(MySource())
"""

from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.registry import source_registry  # noqa: F401
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource

source_registry.register(SentinelSource())
source_registry.register(ElasticSource())
source_registry.register(SplunkSource())
