# How to Add an Enrichment Provider

This guide walks through adding a new enrichment provider to Calseta AI. By the end, your provider will be queried automatically during the alert enrichment pipeline and available for on-demand enrichment via `POST /v1/enrichments`.

---

## Architecture Overview

Enrichment providers are called by the `EnrichmentService` to look up threat intelligence for indicators of compromise (IOCs) extracted from alerts. Each provider handles specific indicator types (IP, domain, hash, account, etc.) and returns structured results.

```
Alert Ingested
    │
    ├─ enrich_alert task (worker queue)
    │       │
    │       ├─ For each indicator:
    │       │     ├─ Check cache (enrichment:{provider}:{type}:{value})
    │       │     ├─ If miss: call provider.enrich(value, type) concurrently
    │       │     ├─ Cache successful results for TTL
    │       │     └─ Aggregate malice verdict (worst wins)
    │       │
    │       └─ Update indicator.enrichment_results, indicator.malice
    │
    └─ POST /v1/enrichments (on-demand, synchronous)
            └─ Same flow, single indicator, returns results immediately
```

All providers run concurrently via `asyncio.gather()`. A single provider failure never blocks other providers or other indicators.

---

## Step 1: Research the Provider API

**Before writing any code**, fetch and analyze the official API documentation. Create `docs/integrations/{name}/api_notes.md` with:

- API base URL and version
- Authentication method (API key header, bearer token, OAuth2)
- Endpoint paths for each indicator type
- Response schema and which fields are useful for SOC analysts
- Rate limits and error codes
- How to derive a malice verdict from the response

This is mandatory. See existing examples:

- `docs/integrations/virustotal/api_notes.md`
- `docs/integrations/abuseipdb/api_notes.md`
- `docs/integrations/okta/api_notes.md`
- `docs/integrations/entra/api_notes.md`

---

## Step 2: Understand the Base Class

The base class lives at `app/integrations/enrichment/base.py`:

```python
class EnrichmentProviderBase(ABC):
    provider_name: str                    # Unique lowercase identifier
    display_name: str                     # Human-readable name
    supported_types: list[IndicatorType]  # Which indicator types this provider handles
    cache_ttl_seconds: int = 3600         # Default TTL; per-type TTLs preferred

    _TTL_BY_TYPE: dict[IndicatorType, int] = {}  # Per-type TTL overrides

    @abstractmethod
    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    def get_cache_ttl(self, indicator_type: IndicatorType) -> int:
        """Return TTL for the given type (checks _TTL_BY_TYPE, then DEFAULT_TTL_BY_TYPE)."""
        ...
```

### Method Contracts

#### `async def enrich(value, indicator_type) -> EnrichmentResult`

- **MUST NEVER RAISE.** This is the most important contract. Catch all exceptions and return `EnrichmentResult.failure_result(self.provider_name, str(e))`.
- The entire method body should be inside a `try/except Exception` block.
- Check `is_configured()` first and return `EnrichmentResult.skipped_result(...)` if not configured.
- Check `indicator_type in self.supported_types` and return `skipped_result` if unsupported.
- Make the HTTP call using `httpx.AsyncClient`.
- Build an `extracted` dict with the fields agents need (structured, concise).
- Store the full API response as `raw` (for debugging and advanced use cases).
- Always include a `malice` key in `extracted` with one of: `"Pending"`, `"Benign"`, `"Suspicious"`, `"Malicious"`.

#### `def is_configured() -> bool`

- Return `True` if all required environment variables are set.
- Called by the registry's `list_configured()` to filter ready providers.
- Never raises -- return `False` on any error.
- Pattern: `return bool(settings.MY_API_KEY)` or `return bool(settings.MY_DOMAIN and settings.MY_TOKEN)`.

---

## Step 3: Add Environment Variables to Config

Add your provider's API key/credentials to `app/config.py` in the "Enrichment Providers" section:

```python
# In app/config.py, class Settings:

# ------------------------------------------------------------------
# Enrichment Providers
# ------------------------------------------------------------------
VIRUSTOTAL_API_KEY: str = ""
ABUSEIPDB_API_KEY: str = ""
OKTA_DOMAIN: str = ""
OKTA_API_TOKEN: str = ""
ENTRA_TENANT_ID: str = ""
ENTRA_CLIENT_ID: str = ""
ENTRA_CLIENT_SECRET: str = ""
IPINFO_API_TOKEN: str = ""  # <-- Add your provider
```

Empty string means "not configured." The provider's `is_configured()` checks for non-empty values.

---

## Step 4: Create the Provider Plugin

Create `app/integrations/enrichment/{name}.py`. Here is a complete worked example for a fictional IPInfo provider:

```python
# app/integrations/enrichment/ipinfo.py
"""
IPInfo enrichment provider.

API: IPInfo v2 (https://ipinfo.io/developers)
Auth: Bearer token (Authorization: Bearer {token})
Supports: IP, domain

For IP addresses: returns geolocation, ASN, company, privacy detection.
For domains: resolves to IP first, then enriches the IP (IPInfo is IP-centric).

Field mapping reference: docs/integrations/ipinfo/api_notes.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.config import settings
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_BASE_URL = "https://ipinfo.io"
_REQUEST_TIMEOUT = 30.0

# Per-type cache TTLs (IP data changes slowly; domain resolution may change faster)
_TTL_MAP: dict[IndicatorType, int] = {
    IndicatorType.IP: 3600,       # 1 hour
    IndicatorType.DOMAIN: 1800,   # 30 minutes
}


def _derive_malice(privacy: dict[str, Any]) -> str:
    """
    Derive malice verdict from IPInfo privacy detection fields.

    IPInfo's privacy block contains: vpn, proxy, tor, relay, hosting.
    - Tor exit node → Suspicious (not inherently malicious, but notable)
    - Known proxy/VPN + hosting → Suspicious
    - Clean IP → Benign
    """
    if not privacy:
        return "Benign"
    if privacy.get("tor", False):
        return "Suspicious"
    if privacy.get("proxy", False) and privacy.get("hosting", False):
        return "Suspicious"
    return "Benign"


class IPInfoProvider(EnrichmentProviderBase):
    """Enrichment provider for IPInfo API."""

    provider_name = "ipinfo"
    display_name = "IPInfo"
    supported_types = [IndicatorType.IP, IndicatorType.DOMAIN]
    cache_ttl_seconds = 3600
    _TTL_BY_TYPE = _TTL_MAP

    def is_configured(self) -> bool:
        """Return True if the IPInfo API token is set."""
        return bool(settings.IPINFO_API_TOKEN)

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Query IPInfo for the given IP address or domain.

        Must never raise — all exceptions returned as failure_result.
        """
        try:
            # Guard: not configured
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name, "IPInfo API token not configured"
                )

            # Guard: unsupported indicator type
            if indicator_type not in self.supported_types:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"IPInfo does not support indicator type '{indicator_type}'",
                )

            # Build URL — IPInfo uses the same endpoint for IPs and domains
            url = f"{_BASE_URL}/{value}"

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {settings.IPINFO_API_TOKEN}"},
                    params={"token": settings.IPINFO_API_TOKEN},
                )

            # Handle 404 — value not found in IPInfo
            if response.status_code == 404:
                return EnrichmentResult.success_result(
                    provider_name=self.provider_name,
                    extracted={"found": False, "malice": "Pending"},
                    raw={"status_code": 404},
                    enriched_at=datetime.now(UTC),
                )

            # Handle rate limiting
            if response.status_code == 429:
                return EnrichmentResult.failure_result(
                    self.provider_name, "IPInfo rate limit exceeded"
                )

            # Handle other HTTP errors
            if response.status_code != 200:
                return EnrichmentResult.failure_result(
                    self.provider_name,
                    f"IPInfo returned HTTP {response.status_code}",
                )

            # Parse response
            body = response.json()
            privacy = body.get("privacy", {})

            extracted: dict[str, Any] = {
                "found": True,
                "ip": body.get("ip"),
                "hostname": body.get("hostname"),
                "city": body.get("city"),
                "region": body.get("region"),
                "country": body.get("country"),
                "org": body.get("org"),       # "AS15169 Google LLC"
                "postal": body.get("postal"),
                "timezone": body.get("timezone"),
                # Privacy detection
                "is_vpn": privacy.get("vpn", False),
                "is_proxy": privacy.get("proxy", False),
                "is_tor": privacy.get("tor", False),
                "is_relay": privacy.get("relay", False),
                "is_hosting": privacy.get("hosting", False),
                # Malice verdict
                "malice": _derive_malice(privacy),
            }

            # Include ASN details if present
            asn = body.get("asn", {})
            if asn:
                extracted["asn"] = asn.get("asn")
                extracted["asn_name"] = asn.get("name")
                extracted["asn_domain"] = asn.get("domain")
                extracted["asn_type"] = asn.get("type")

            # Include company details if present
            company = body.get("company", {})
            if company:
                extracted["company_name"] = company.get("name")
                extracted["company_domain"] = company.get("domain")
                extracted["company_type"] = company.get("type")

            return EnrichmentResult.success_result(
                provider_name=self.provider_name,
                extracted=extracted,
                raw=body,
                enriched_at=datetime.now(UTC),
            )

        except Exception as exc:
            logger.exception(
                "ipinfo_enrich_error",
                indicator_type=str(indicator_type),
                value=value[:64],  # Truncate for log safety
            )
            return EnrichmentResult.failure_result(self.provider_name, str(exc))
```

### Key Patterns to Follow

#### 1. The No-Raise Contract

The entire `enrich()` method body is inside `try/except Exception`. This is non-negotiable. The enrichment pipeline runs all providers concurrently. If one raises, it would propagate up and potentially crash the task. The contract says: **always return an `EnrichmentResult`, even on failure.**

```python
async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
    try:
        # ... all logic here ...
    except Exception as exc:
        logger.exception("provider_enrich_error", value=value[:64])
        return EnrichmentResult.failure_result(self.provider_name, str(exc))
```

#### 2. Guard Clauses at the Top

Always check configuration and type support before making any HTTP call:

```python
if not self.is_configured():
    return EnrichmentResult.skipped_result(self.provider_name, "API key not configured")

if indicator_type not in self.supported_types:
    return EnrichmentResult.skipped_result(self.provider_name, f"Unsupported type: {indicator_type}")
```

#### 3. httpx.AsyncClient Pattern

Use `httpx.AsyncClient` as a context manager with a timeout:

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(url, headers=headers, params=params)
```

Do not create a module-level client. Each `enrich()` call creates a short-lived client. This avoids connection pool issues and is safe for concurrent use.

#### 4. HTTP Status Code Handling

Handle these cases explicitly:

| Status | Meaning | Return |
|---|---|---|
| `200` | Success | `EnrichmentResult.success_result(...)` |
| `404` | Not found | `success_result` with `extracted={"found": False, "malice": "Pending"}` |
| `429` | Rate limited | `failure_result` with descriptive message |
| Other | Error | `failure_result` with status code in message |

Note that 404 is **success** with `found=False` -- the provider worked correctly, the value just was not in their database. This distinction matters for malice aggregation.

#### 5. The `extracted` Dict

The `extracted` dict is the structured subset surfaced to AI agents. Design it for agent consumption:

- Use clear, lowercase snake_case key names.
- Include a `malice` key with one of: `"Pending"`, `"Benign"`, `"Suspicious"`, `"Malicious"`.
- Include a `found` boolean when the concept applies (account lookup, hash lookup).
- Keep it flat -- avoid nested objects in `extracted`. Nesting belongs in `raw`.
- Include only fields an agent would actually use for investigation.

#### 6. The `raw` Dict

Store the full API response as `raw`. This is persisted in `indicators.enrichment_results` but NOT included in agent-facing API responses by default. It is available for debugging and for custom field extraction rules.

#### 7. Malice Verdict Derivation

Every provider must derive a `malice` value from its response. The enrichment engine aggregates verdicts across all providers using worst-wins ordering:

```
Malicious(3) > Suspicious(2) > Benign(1) > Pending(0)
```

Map your provider's native scoring to one of these four values. Be explicit about thresholds. Examples from existing providers:

| Provider | Malicious | Suspicious | Benign |
|---|---|---|---|
| VirusTotal | `malicious > 0` | `suspicious > 0` | Otherwise |
| AbuseIPDB | Score >= 75 | Score >= 25 | Score < 25 |
| Okta / Entra | N/A (account lookup, no score) | N/A | N/A |

---

## Step 5: Register the Provider

Edit `app/integrations/enrichment/__init__.py`:

```python
# app/integrations/enrichment/__init__.py
"""
Enrichment provider package — registers all built-in providers.

Import order matters: registry must be imported before providers are registered.
"""

from app.integrations.enrichment.abuseipdb import AbuseIPDBProvider
from app.integrations.enrichment.entra import EntraProvider
from app.integrations.enrichment.ipinfo import IPInfoProvider  # <-- Add import
from app.integrations.enrichment.okta import OktaProvider
from app.integrations.enrichment.registry import enrichment_registry
from app.integrations.enrichment.virustotal import VirusTotalProvider

enrichment_registry.register(VirusTotalProvider())
enrichment_registry.register(AbuseIPDBProvider())
enrichment_registry.register(OktaProvider())
enrichment_registry.register(EntraProvider())
enrichment_registry.register(IPInfoProvider())  # <-- Add registration
```

That is all. The provider is now active. The enrichment engine will automatically query it for indicators matching its `supported_types` list, as long as `is_configured()` returns `True`.

---

## Step 6: Cache Key Format and TTL

### Cache Key Format

Cache keys follow a deterministic format defined in `app/cache/keys.py`:

```
enrichment:{provider_name}:{indicator_type}:{value}
```

Examples:
```
enrichment:ipinfo:ip:198.51.100.77
enrichment:ipinfo:domain:evil.example.com
enrichment:virustotal:hash_sha256:a1b2c3d4...
```

You do not need to construct cache keys yourself. The `EnrichmentService` handles caching automatically:

1. Before calling `provider.enrich()`, it checks the cache.
2. If a cached result exists and is not expired, it skips the API call.
3. After a successful `enrich()`, it caches the result for the provider's TTL.

### TTL Configuration

TTL is resolved in this order:

1. Provider's `_TTL_BY_TYPE` dict (per-type overrides specific to this provider)
2. `DEFAULT_TTL_BY_TYPE` from `app/integrations/enrichment/base.py` (global defaults)
3. Provider's `cache_ttl_seconds` class attribute (fallback)

Default TTLs by indicator type:

| Type | Default TTL | Rationale |
|---|---|---|
| IP | 3600s (1h) | IP reputation changes frequently |
| Domain | 21600s (6h) | Domain reputation changes less often |
| Hash (MD5/SHA1/SHA256) | 86400s (24h) | File hashes are immutable |
| URL | 1800s (30m) | URLs can be taken down or rotated quickly |
| Email | 3600s (1h) | Email reputation moderate volatility |
| Account | 900s (15m) | Account status can change rapidly |

To override TTLs for your provider, set the `_TTL_BY_TYPE` class variable:

```python
_TTL_MAP: dict[IndicatorType, int] = {
    IndicatorType.IP: 3600,
    IndicatorType.DOMAIN: 1800,  # Shorter than default if your source updates fast
}

class IPInfoProvider(EnrichmentProviderBase):
    _TTL_BY_TYPE = _TTL_MAP
```

---

## Step 7: How the Enrichment Pipeline Uses Your Provider

### Automatic (Alert Enrichment)

When an alert is ingested:

1. The ingest route enqueues an `enrich_alert` task to the `enrichment` queue.
2. The worker picks up the task and calls `EnrichmentService.enrich_alert(alert_id)`.
3. The service loads all indicators for the alert.
4. For each indicator, it calls `enrichment_registry.list_for_type(indicator_type)` to get all configured providers that support that type.
5. All providers for all indicators run concurrently via `asyncio.gather()`.
6. Results are cached and persisted to `indicators.enrichment_results`.
7. The worst malice verdict across all providers is set on the indicator.

### On-Demand (`POST /v1/enrichments`)

Agents or humans can enrich a single indicator synchronously:

```bash
curl -X POST https://calseta.example.com/v1/enrichments \
  -H "Authorization: Bearer cai_xxxx" \
  -H "Content-Type: application/json" \
  -d '{"type": "ip", "value": "198.51.100.77"}'
```

This calls the same `EnrichmentService.enrich_indicator()` method, with cache checking. Results are returned immediately in the response.

### Provider Listing (`GET /v1/enrichments/providers`)

All registered providers (configured and unconfigured) are listed at this endpoint. Your provider will appear automatically after registration.

---

## Step 8: Write Unit Tests

Create `tests/test_ipinfo_provider.py` following the established pattern:

```python
"""
Unit tests for the IPInfo enrichment provider.

httpx.AsyncClient is patched so no real HTTP calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.enrichment.ipinfo import IPInfoProvider
from app.schemas.enrichment import EnrichmentStatus
from app.schemas.indicators import IndicatorType


def _mock_response(status_code: int, body: object) -> MagicMock:
    """Build a minimal fake httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def _mock_async_client(*responses: MagicMock) -> MagicMock:
    """
    Return a mock httpx.AsyncClient context manager that yields a client
    whose get() returns responses in sequence.
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    if len(responses) == 1:
        mock_client.get.return_value = responses[0]
    else:
        mock_client.get.side_effect = list(responses)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


class TestIPInfoProvider:
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> IPInfoProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.ipinfo.settings.IPINFO_API_TOKEN",
            "test-ipinfo-token",
        )
        return IPInfoProvider()

    # -- Successful enrichment --

    async def test_ip_clean(self, provider: IPInfoProvider) -> None:
        body = {
            "ip": "8.8.8.8",
            "hostname": "dns.google",
            "city": "Mountain View",
            "region": "California",
            "country": "US",
            "org": "AS15169 Google LLC",
            "postal": "94035",
            "timezone": "America/Los_Angeles",
            "privacy": {
                "vpn": False,
                "proxy": False,
                "tor": False,
                "relay": False,
                "hosting": False,
            },
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("8.8.8.8", IndicatorType.IP)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["malice"] == "Benign"
        assert result.extracted["country"] == "US"
        assert result.extracted["is_tor"] is False

    async def test_ip_tor_exit(self, provider: IPInfoProvider) -> None:
        body = {
            "ip": "185.220.101.32",
            "city": "Nuremberg",
            "country": "DE",
            "org": "AS24940 Hetzner Online GmbH",
            "privacy": {
                "vpn": False,
                "proxy": False,
                "tor": True,
                "relay": False,
                "hosting": True,
            },
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("185.220.101.32", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"
        assert result.extracted["is_tor"] is True

    async def test_ip_proxy_hosting(self, provider: IPInfoProvider) -> None:
        body = {
            "ip": "104.28.10.50",
            "country": "US",
            "privacy": {
                "vpn": False,
                "proxy": True,
                "tor": False,
                "relay": False,
                "hosting": True,
            },
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("104.28.10.50", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"

    # -- Not found --

    async def test_ip_not_found(self, provider: IPInfoProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))):
            result = await provider.enrich("0.0.0.0", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False
        assert result.extracted["malice"] == "Pending"

    # -- HTTP errors --

    async def test_rate_limited(self, provider: IPInfoProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(429, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "rate limit" in (result.error_message or "").lower()

    async def test_http_error(self, provider: IPInfoProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(500, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    # -- Not configured --

    async def test_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.ipinfo.settings.IPINFO_API_TOKEN", ""
        )
        provider = IPInfoProvider()
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    # -- Unsupported type --

    async def test_unsupported_type(self, provider: IPInfoProvider) -> None:
        result = await provider.enrich("user@example.com", IndicatorType.EMAIL)

        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    # -- is_configured --

    def test_is_configured_true(self, provider: IPInfoProvider) -> None:
        assert provider.is_configured() is True

    def test_is_configured_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.ipinfo.settings.IPINFO_API_TOKEN", ""
        )
        provider = IPInfoProvider()
        assert provider.is_configured() is False

    # -- Exception handling --

    async def test_exception_returns_failure(self, provider: IPInfoProvider) -> None:
        """Verify the no-raise contract: exceptions become failure_result."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = ConnectionError("DNS resolution failed")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "DNS resolution failed" in (result.error_message or "")

    # -- Domain enrichment --

    async def test_domain_enrichment(self, provider: IPInfoProvider) -> None:
        body = {
            "ip": "93.184.216.34",
            "hostname": "example.com",
            "city": "Norwell",
            "region": "Massachusetts",
            "country": "US",
            "org": "AS15133 Edgecast Inc.",
            "privacy": {
                "vpn": False,
                "proxy": False,
                "tor": False,
                "relay": False,
                "hosting": True,
            },
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("example.com", IndicatorType.DOMAIN)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is True
```

### Test Pattern Summary

Every enrichment provider test file should cover:

| Test | What it verifies |
|---|---|
| Successful enrichment (benign) | Correct field extraction, `malice == "Benign"` |
| Successful enrichment (suspicious) | Threshold logic for `"Suspicious"` verdict |
| Successful enrichment (malicious) | Threshold logic for `"Malicious"` verdict (if applicable) |
| Not found (404) | `success=True`, `found=False`, `malice="Pending"` |
| Rate limited (429) | `success=False`, `status=FAILED` |
| HTTP error (other) | `success=False`, `status=FAILED` |
| Not configured | `status=SKIPPED` |
| Unsupported type | `status=SKIPPED` |
| Exception handling | Exception becomes `failure_result` (no-raise contract) |
| `is_configured()` true/false | Returns correct boolean |

### Mock Pattern

The test helper `_mock_async_client()` creates a mock `httpx.AsyncClient` context manager:

```python
def _mock_async_client(*responses):
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    if len(responses) == 1:
        mock_client.get.return_value = responses[0]
    else:
        mock_client.get.side_effect = list(responses)

    return MagicMock(return_value=mock_client)
```

Use it with `unittest.mock.patch`:

```python
with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
    result = await provider.enrich("1.2.3.4", IndicatorType.IP)
```

For providers that need multiple sequential API calls (e.g., Okta: user lookup + groups fetch), pass multiple responses:

```python
with patch("httpx.AsyncClient", _mock_async_client(user_resp, groups_resp)):
    result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)
```

Use `monkeypatch.setattr()` to configure provider settings:

```python
monkeypatch.setattr(
    "app.integrations.enrichment.ipinfo.settings.IPINFO_API_TOKEN",
    "test-token",
)
```

---

## Step 9: Run Tests and Lint

```bash
# Run only your provider tests
pytest tests/test_ipinfo_provider.py -v

# Run all enrichment tests
pytest tests/test_enrichment_providers.py tests/test_enrichment_service.py -v

# Full quality checks
make lint       # ruff
make typecheck  # mypy
make test       # all tests
```

---

## Complete Checklist

1. [ ] Create `docs/integrations/ipinfo/api_notes.md` with field mapping research
2. [ ] Add env var(s) to `app/config.py` (e.g., `IPINFO_API_TOKEN: str = ""`)
3. [ ] Create `app/integrations/enrichment/ipinfo.py` implementing `EnrichmentProviderBase`
4. [ ] Register in `app/integrations/enrichment/__init__.py`
5. [ ] Create `tests/test_ipinfo_provider.py` with full test coverage
6. [ ] Run `make lint`, `make typecheck`, `make test` -- all pass

---

## Common Pitfalls

### 1. Raising exceptions from enrich()

This is the single most critical contract. If `enrich()` raises, it can crash the entire enrichment pipeline for an alert. The outer `try/except Exception` block is mandatory.

### 2. Forgetting the malice key in extracted

The enrichment engine looks for `extracted["malice"]` to aggregate the worst verdict across providers. If your provider does not include this key, the indicator's malice stays at `"Pending"` regardless of your findings. Always include `"malice"` in the `extracted` dict.

### 3. Returning failure_result for 404 responses

A 404 means the provider successfully looked up the value and it was not found. This is `success=True` with `extracted={"found": False, "malice": "Pending"}`. Only return `failure_result` for actual errors (5xx, timeouts, auth failures).

### 4. Using a module-level httpx client

Do not create `httpx.AsyncClient` at module level. The async event loop may not exist at import time. Always create it inside `enrich()` as a context manager.

### 5. Not truncating values in log messages

Indicator values can be long (URLs, hashes). Always truncate in log calls: `value=value[:64]`. This prevents log line explosion and avoids accidentally logging sensitive data.

### 6. Duplicate provider_name registration

Each `provider_name` must be globally unique. The registry raises `ValueError` on duplicates. Choose a distinctive lowercase name that matches your integration.

### 7. Not handling rate limits explicitly

Rate limit (429) responses should return `failure_result` with a descriptive message. The enrichment engine will retry on the next alert enrichment cycle. Do not implement retry logic inside the provider -- the cache and pipeline handle retries at a higher level.

---

## Reference: EnrichmentResult Factory Methods

```python
class EnrichmentResult(BaseModel):
    provider_name: str
    status: EnrichmentStatus     # success, failed, skipped
    success: bool

    extracted: dict | None       # Structured fields for agents
    raw: dict | None             # Full API response
    enriched_at: datetime | None

    error_message: str | None

    @classmethod
    def success_result(cls, provider_name, extracted, raw, enriched_at) -> EnrichmentResult: ...

    @classmethod
    def failure_result(cls, provider_name, error) -> EnrichmentResult: ...

    @classmethod
    def skipped_result(cls, provider_name, reason) -> EnrichmentResult: ...
```

Use the factory methods -- do not construct `EnrichmentResult` directly.

---

## Reference: Existing Enrichment Providers

| File | Provider | Auth | Supported Types | Malice Logic |
|---|---|---|---|---|
| `virustotal.py` | VirusTotal v3 | `x-apikey` header | IP, domain, MD5, SHA1, SHA256 | `malicious > 0` / `suspicious > 0` / Benign |
| `abuseipdb.py` | AbuseIPDB v2 | `Key` header | IP | Score >= 75 / >= 25 / < 25 |
| `okta.py` | Okta Management API | `SSWS` bearer token | Account | N/A (account lookup only) |
| `entra.py` | Microsoft Graph v1.0 | OAuth2 client credentials | Account | N/A (account lookup only) |

---

## Reference: IndicatorType Values

```python
class IndicatorType(StrEnum):
    IP = "ip"
    DOMAIN = "domain"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    URL = "url"
    EMAIL = "email"
    ACCOUNT = "account"
```
