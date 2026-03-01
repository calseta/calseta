"""
Alert source plugin package.

All built-in sources are imported and registered here at package import time.
The ingest endpoint imports source_registry from this package.

Adding a new source:
    1. Create app/integrations/sources/{name}.py with MySource(AlertSourceBase)
    2. Add: from app.integrations.sources.{name} import MySource
    3. Add: source_registry.register(MySource())
"""

from app.integrations.sources.registry import source_registry  # noqa: F401

# Built-in source registrations — added by chunks 2.2, 2.3, 2.4
