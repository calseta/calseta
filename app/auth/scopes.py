"""
Scope definitions for Calseta API key authorization.

`admin` is a superscope — an API key with `admin` scope passes every
scope check without needing to enumerate individual scopes.
"""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    ALERTS_READ = "alerts:read"
    ALERTS_WRITE = "alerts:write"
    ENRICHMENTS_READ = "enrichments:read"
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_WRITE = "workflows:write"
    WORKFLOWS_EXECUTE = "workflows:execute"
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"
    ADMIN = "admin"
