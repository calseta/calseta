# How to Add an Alert Source Plugin

This guide walks through adding a new alert source integration to Calseta AI. By the end, your source will accept webhook payloads, normalize them to the Calseta agent-native schema, extract indicators, and flow through the full enrichment pipeline.

---

## Architecture Overview

Every alert enters Calseta through a **source plugin** — a class that subclasses `AlertSourceBase` and implements four methods. The platform handles everything else: persistence, enrichment, deduplication, activity logging, and agent dispatch.

```
Webhook → POST /v1/ingest/{source_name}
              │
              ├─ verify_webhook_signature(headers, raw_body)
              ├─ validate_payload(raw)
              ├─ normalize(raw) → CalsetaAlert
              ├─ extract_indicators(raw) → list[IndicatorExtract]
              ├─ extract_detection_rule_ref(raw) → str | None
              │
              └─ AlertIngestionService.ingest()
                    ├─ Persist alert + raw_payload
                    ├─ Associate detection rule
                    ├─ Enqueue enrichment task
                    └─ Write activity event
```

The ingest endpoint returns `202 Accepted` within 200ms. All enrichment and dispatch happens asynchronously via the task queue.

---

## Step 1: Research the Source API

**Before writing any code**, fetch and analyze the official API documentation for your source. Create `docs/integrations/{name}/api_notes.md` with:

- Field names and types from the webhook payload
- Severity values and how they map to Calseta severity
- Timestamp formats
- Which fields contain indicators (IPs, domains, hashes, accounts, URLs)
- Webhook signature mechanism (HMAC-SHA256, bearer token, or none)
- Rate limits and edge cases

This is mandatory. See existing examples:

- `docs/integrations/sentinel/api_notes.md`
- `docs/integrations/elastic/api_notes.md`
- `docs/integrations/splunk/api_notes.md`

---

## Step 2: Understand the Base Class

The base class lives at `app/integrations/sources/base.py`:

```python
class AlertSourceBase(ABC):
    source_name: str       # Unique lowercase identifier, used in URL path
    display_name: str      # Human-readable name for API responses and logs

    @abstractmethod
    def validate_payload(self, raw: dict) -> bool: ...

    @abstractmethod
    def normalize(self, raw: dict) -> CalsetaAlert: ...

    @abstractmethod
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]: ...

    def extract_detection_rule_ref(self, raw: dict) -> str | None:
        return None

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        # Default: returns True and logs a warning
        return True
```

### Method Contracts

#### `validate_payload(raw: dict) -> bool`

- Called before `normalize()` to guard against malformed payloads.
- **Must not raise.** Catch all exceptions internally and return `False`.
- Return `True` only if the payload has the minimum required structure for this source.
- Check for the existence of distinguishing fields (e.g., Sentinel has `properties.title`, Elastic has `kibana.alert.rule.name`).

#### `normalize(raw: dict) -> CalsetaAlert`

- Map the raw source payload to the Calseta agent-native schema.
- The returned `CalsetaAlert` **must** set `source_name = self.source_name`.
- Source-specific fields that don't map to `CalsetaAlert` are preserved in `raw_payload` automatically by the ingest service layer. Do not try to capture them here.
- Required fields: `title`, `severity` (an `AlertSeverity` enum value), `occurred_at` (timezone-aware `datetime`), `source_name`.
- Optional normalized fields used by Pass 2 indicator extraction: `src_ip`, `dst_ip`, `src_hostname`, `dst_hostname`, `file_hash_md5`, `file_hash_sha256`, `file_hash_sha1`, `actor_email`, `actor_username`, `dns_query`, `http_url`, `http_hostname`, `email_from`, `email_reply_to`.

#### `extract_indicators(raw: dict) -> list[IndicatorExtract]`

- Extract indicators of compromise directly from the raw payload (Pass 1 of the 3-pass extraction pipeline).
- **Must not raise.** Return an empty list if extraction fails.
- Each `IndicatorExtract` has: `type` (`IndicatorType` enum), `value` (string), and optional `source_field` (for logging which field it came from).
- Valid indicator types: `ip`, `domain`, `hash_md5`, `hash_sha1`, `hash_sha256`, `url`, `email`, `account`.
- Deduplication by `(type, value)` happens downstream. It is safe to return duplicates.

#### `extract_detection_rule_ref(raw: dict) -> str | None` (optional)

- Return a source-specific detection rule identifier string.
- Used to look up or auto-create a `DetectionRule` record and associate it with the alert.
- Default implementation returns `None` (no rule association).
- Override if your source provides rule references (e.g., a rule UUID, saved search name, or correlation rule ID).

#### `verify_webhook_signature(headers: dict[str, str], raw_body: bytes) -> bool` (optional)

- Called before `validate_payload()`. If this returns `False`, the endpoint returns `401 Unauthorized`.
- Default implementation returns `True` (no verification, logs a warning).
- When implementing: **always use `hmac.compare_digest()`** for comparisons, never `==`.
- Pattern: check if the secret env var is set. If not set, return `True` (allows unconfigured deployments). If set but the header is missing or invalid, return `False`.

---

## Step 3: Add the Webhook Secret to Config

If your source supports webhook signing, add the secret to `app/config.py` in the "Webhook Signing Secrets" section:

```python
# In app/config.py, class Settings:

# ------------------------------------------------------------------
# Webhook Signing Secrets
# ------------------------------------------------------------------
SENTINEL_WEBHOOK_SECRET: str = ""
ELASTIC_WEBHOOK_SECRET: str = ""
SPLUNK_WEBHOOK_SECRET: str = ""
GUARDDUTY_WEBHOOK_SECRET: str = ""  # <-- Add your source
```

Empty string means "not configured" and the signature check is skipped.

---

## Step 4: Create the Source Plugin

Create `app/integrations/sources/{name}.py`. Here is a complete worked example for a fictional AWS GuardDuty source:

```python
# app/integrations/sources/guardduty.py
"""
AWS GuardDuty source integration.

Normalizes GuardDuty finding JSON payloads to the Calseta agent-native schema.
GuardDuty findings are sent via EventBridge → API Gateway → webhook, or via
SNS → Lambda → webhook, as a JSON object with the GuardDuty finding format.

Field mapping reference: docs/integrations/guardduty/api_notes.md
"""

from __future__ import annotations

import hashlib
import hmac
from contextlib import suppress
from datetime import datetime

import structlog

from app.config import settings
from app.integrations.sources.base import AlertSourceBase
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

logger = structlog.get_logger(__name__)

# GuardDuty severity ranges → Calseta severity
# GuardDuty uses numeric severity: 0-3.9 Low, 4-6.9 Medium, 7-8.9 High, 9+ maps to Critical
# See: https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings.html


def _map_severity(raw_severity: float | int | None) -> AlertSeverity:
    """Map GuardDuty numeric severity (0-10) to Calseta AlertSeverity."""
    if raw_severity is None:
        return AlertSeverity.PENDING
    sev = float(raw_severity)
    if sev >= 9.0:
        return AlertSeverity.CRITICAL
    if sev >= 7.0:
        return AlertSeverity.HIGH
    if sev >= 4.0:
        return AlertSeverity.MEDIUM
    if sev >= 1.0:
        return AlertSeverity.LOW
    return AlertSeverity.INFORMATIONAL


class GuardDutySource(AlertSourceBase):
    """Alert source plugin for AWS GuardDuty finding webhooks."""

    source_name = "guardduty"
    display_name = "AWS GuardDuty"

    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """
        Return True if the payload looks like a GuardDuty finding.

        GuardDuty findings have: detail.type, detail.severity, detail.resource.
        The top-level key may be "detail" (EventBridge) or the finding itself (direct).
        """
        try:
            detail = raw.get("detail", raw)
            return bool(detail.get("type") and detail.get("severity") is not None)
        except Exception:
            return False

    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """Map GuardDuty finding fields to CalsetaAlert."""
        # Handle both EventBridge wrapper and direct finding format
        detail = raw.get("detail", raw)

        # Title: GuardDuty "title" field, fallback to finding type
        title = detail.get("title") or detail.get("type") or "Untitled GuardDuty Finding"

        # Severity: numeric float 0-10
        severity = _map_severity(detail.get("severity"))

        # occurred_at: ISO 8601 updatedAt or createdAt
        occurred_at_str = detail.get("updatedAt") or detail.get("createdAt")
        occurred_at = datetime.now().astimezone()
        if occurred_at_str:
            with suppress(ValueError, TypeError):
                occurred_at = datetime.fromisoformat(
                    str(occurred_at_str).replace("Z", "+00:00")
                )

        # Tags from GuardDuty tags map + finding type prefix
        tags: list[str] = []
        finding_type = detail.get("type", "")
        if finding_type:
            # e.g. "Recon:EC2/PortProbeUnprotectedPort" → tag "Recon"
            prefix = finding_type.split(":")[0] if ":" in finding_type else ""
            if prefix:
                tags.append(prefix)

        resource_tags = detail.get("resource", {}).get("tags", [])
        if isinstance(resource_tags, list):
            for tag in resource_tags:
                if isinstance(tag, dict) and tag.get("value"):
                    tags.append(str(tag["value"]))

        return CalsetaAlert(
            title=str(title),
            severity=severity,
            occurred_at=occurred_at,
            source_name=self.source_name,
            tags=tags,
            # Populate normalized fields for Pass 2 extraction
            src_ip=self._extract_remote_ip(detail),
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract IOCs from GuardDuty finding resource and service details.

        Handles:
          - Remote IP (service.action.networkConnectionAction.remoteIpDetails.ipAddressV4)
          - Local IP (service.action.networkConnectionAction.localIpDetails.ipAddressV4)
          - DNS domain (service.action.dnsRequestAction.domain)
          - S3 bucket names and EC2 instance IDs are NOT indicators — skip them.
        """
        indicators: list[IndicatorExtract] = []
        detail = raw.get("detail", raw)
        service = detail.get("service", {})
        action = service.get("action", {})

        # Network connection action — remote and local IPs
        net_action = action.get("networkConnectionAction", {})
        remote_ip = (
            net_action.get("remoteIpDetails", {}).get("ipAddressV4")
        )
        if remote_ip:
            indicators.append(
                IndicatorExtract(
                    type=IndicatorType.IP,
                    value=remote_ip,
                    source_field="service.action.networkConnectionAction.remoteIpDetails.ipAddressV4",
                )
            )

        local_ip = (
            net_action.get("localIpDetails", {}).get("ipAddressV4")
        )
        if local_ip:
            indicators.append(
                IndicatorExtract(
                    type=IndicatorType.IP,
                    value=local_ip,
                    source_field="service.action.networkConnectionAction.localIpDetails.ipAddressV4",
                )
            )

        # DNS request action — domain
        dns_domain = action.get("dnsRequestAction", {}).get("domain")
        if dns_domain:
            indicators.append(
                IndicatorExtract(
                    type=IndicatorType.DOMAIN,
                    value=dns_domain,
                    source_field="service.action.dnsRequestAction.domain",
                )
            )

        # Port probe action — remote IP
        port_probe = action.get("portProbeAction", {})
        for probe in port_probe.get("portProbeDetails", []):
            if isinstance(probe, dict):
                pp_ip = probe.get("remoteIpDetails", {}).get("ipAddressV4")
                if pp_ip:
                    indicators.append(
                        IndicatorExtract(
                            type=IndicatorType.IP,
                            value=pp_ip,
                            source_field="service.action.portProbeAction.portProbeDetails.remoteIpDetails.ipAddressV4",
                        )
                    )

        # AWS API call action — remote IP
        api_call = action.get("awsApiCallAction", {})
        api_ip = api_call.get("remoteIpDetails", {}).get("ipAddressV4")
        if api_ip:
            indicators.append(
                IndicatorExtract(
                    type=IndicatorType.IP,
                    value=api_ip,
                    source_field="service.action.awsApiCallAction.remoteIpDetails.ipAddressV4",
                )
            )

        # Kubernetes actor — account
        k8s_user = (
            detail.get("resource", {})
            .get("kubernetesDetails", {})
            .get("kubernetesUserDetails", {})
            .get("username")
        )
        if k8s_user:
            indicators.append(
                IndicatorExtract(
                    type=IndicatorType.ACCOUNT,
                    value=k8s_user,
                    source_field="resource.kubernetesDetails.kubernetesUserDetails.username",
                )
            )

        return indicators

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """
        Return the GuardDuty finding type as the detection rule reference.

        Format: "Recon:EC2/PortProbeUnprotectedPort"
        """
        detail = raw.get("detail", raw)
        return detail.get("type") or None

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify HMAC-SHA256 signature in the X-GuardDuty-Signature header.

        Returns True if GUARDDUTY_WEBHOOK_SECRET is not configured.
        Returns False if secret is set but signature is absent or invalid.
        """
        secret = settings.GUARDDUTY_WEBHOOK_SECRET
        if not secret:
            return True

        signature_header = (
            headers.get("X-GuardDuty-Signature")
            or headers.get("x-guardduty-signature")
            or ""
        )
        if not signature_header:
            logger.warning("guardduty_webhook_missing_signature")
            return False

        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        received = signature_header.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_remote_ip(detail: dict) -> str | None:  # type: ignore[type-arg]
        """Extract the primary remote IP for the normalized src_ip field."""
        service = detail.get("service", {})
        action = service.get("action", {})
        for action_key in [
            "networkConnectionAction",
            "portProbeAction",
            "awsApiCallAction",
        ]:
            sub = action.get(action_key, {})
            ip = sub.get("remoteIpDetails", {}).get("ipAddressV4")
            if ip:
                return str(ip)
        return None
```

### Key Patterns to Follow

1. **Severity mapping.** Create a module-level mapping from source severity values to `AlertSeverity` enum values. Handle missing/unknown values by defaulting to `AlertSeverity.PENDING`.

2. **Timestamp parsing.** Always handle missing timestamps gracefully. Use `datetime.now().astimezone()` or `datetime.now(UTC)` as fallback. Use `contextlib.suppress` or try/except for parse errors.

3. **Indicator extraction helpers.** Define small helper functions (`_add`, `_ind`) to reduce repetition when building `IndicatorExtract` lists.

4. **Signature verification pattern.** Always follow this exact pattern:
   - Check if secret env var is empty. If so, return `True`.
   - Check if the signature header is present. If missing, log warning and return `False`.
   - Compute expected HMAC and compare with `hmac.compare_digest()`.

---

## Step 5: Register the Plugin

Edit `app/integrations/sources/__init__.py` to import and register your source:

```python
# app/integrations/sources/__init__.py
"""
Alert source plugin package.

All built-in sources are imported and registered here at package import time.
The ingest endpoint imports source_registry from this package.
"""

from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.generic import GenericSource
from app.integrations.sources.guardduty import GuardDutySource  # <-- Add import
from app.integrations.sources.registry import source_registry  # noqa: F401
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource

source_registry.register(SentinelSource())
source_registry.register(ElasticSource())
source_registry.register(SplunkSource())
source_registry.register(GenericSource())
source_registry.register(GuardDutySource())  # <-- Add registration
```

That is all. The ingest endpoint at `POST /v1/ingest/guardduty` is now live. The `source_name` in the URL path is matched against `source_registry.get("guardduty")` at runtime. No changes to route handlers or the router are needed.

---

## Step 6: How the Ingest Route Works

You do **not** need to create any new route. The existing `POST /v1/ingest/{source_name}` route in `app/api/v1/ingest.py` handles all sources dynamically:

1. Looks up `source_registry.get(source_name)` -- returns your plugin or `404`.
2. Checks API key `allowed_sources` -- rejects with `403` if the source is not in the key's allowed list.
3. Calls `source.verify_webhook_signature(headers, raw_body)` -- returns `401` if invalid.
4. Parses JSON body, calls `source.validate_payload(raw_payload)` -- returns `422` if invalid.
5. Calls `AlertIngestionService.ingest(source, raw_payload, ...)` which:
   - Calls `source.normalize(raw_payload)` to get `CalsetaAlert`
   - Calls `source.extract_indicators(raw_payload)` for Pass 1 extraction
   - Runs Pass 2 extraction (system normalized-field mappings against `CalsetaAlert` fields)
   - Generates a fingerprint, checks for duplicates
   - Persists the alert with `raw_payload` stored as JSONB
   - Calls `source.extract_detection_rule_ref(raw_payload)` and associates the rule
   - Enqueues enrichment to the task queue
6. Returns `202 Accepted` with the alert UUID.

There is also `POST /v1/alerts` for programmatic ingest (no webhook signature verification):

```json
{
  "source_name": "guardduty",
  "payload": { ... the raw GuardDuty finding ... }
}
```

---

## Step 7: Create Test Fixtures

Create a realistic JSON fixture at `tests/fixtures/guardduty_finding.json`:

```json
{
  "version": "0",
  "id": "event-id-12345",
  "detail-type": "GuardDuty Finding",
  "source": "aws.guardduty",
  "account": "123456789012",
  "time": "2024-01-15T10:30:00Z",
  "region": "us-east-1",
  "detail": {
    "schemaVersion": "2.0",
    "accountId": "123456789012",
    "region": "us-east-1",
    "type": "Recon:EC2/PortProbeUnprotectedPort",
    "title": "Unprotected port on EC2 instance i-abc123 is being probed",
    "description": "EC2 instance i-abc123 has an unprotected port being probed by a known malicious host.",
    "severity": 8.5,
    "createdAt": "2024-01-15T10:25:00.000Z",
    "updatedAt": "2024-01-15T10:30:00.000Z",
    "resource": {
      "resourceType": "Instance",
      "instanceDetails": {
        "instanceId": "i-abc123",
        "instanceType": "t3.micro",
        "availabilityZone": "us-east-1a",
        "networkInterfaces": [
          {
            "privateIpAddress": "10.0.1.50",
            "publicIp": "54.200.100.50"
          }
        ]
      },
      "tags": [
        {"key": "Environment", "value": "production"},
        {"key": "Team", "value": "platform"}
      ]
    },
    "service": {
      "serviceName": "guardduty",
      "action": {
        "actionType": "PORT_PROBE",
        "portProbeAction": {
          "portProbeDetails": [
            {
              "localPortDetails": {"port": 22, "portName": "SSH"},
              "remoteIpDetails": {
                "ipAddressV4": "198.51.100.77",
                "organization": {"asn": "12345", "asnOrg": "Suspicious ISP"},
                "country": {"countryName": "Russia"}
              }
            }
          ],
          "blocked": false
        }
      },
      "count": 15,
      "detectorId": "detector-abc"
    }
  }
}
```

Build the fixture from the official API docs, not from imagination. Every field should match the real schema.

---

## Step 8: Write Unit Tests

Create `tests/test_guardduty_source.py` following the established pattern:

```python
"""Tests for the GuardDuty source integration."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.integrations.sources.guardduty import GuardDutySource
from app.schemas.alert import AlertSeverity
from app.schemas.indicators import IndicatorType

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


def _setattr_secret(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setattr(
        "app.integrations.sources.guardduty.settings.GUARDDUTY_WEBHOOK_SECRET", value
    )


class TestGuardDutySource:
    @pytest.fixture
    def source(self) -> GuardDutySource:
        return GuardDutySource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("guardduty_finding.json")

    # -- source_name --
    def test_source_name(self, source: GuardDutySource) -> None:
        assert source.source_name == "guardduty"

    # -- validate_payload --
    def test_validate_payload_valid(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.validate_payload(payload) is True

    def test_validate_payload_invalid(self, source: GuardDutySource) -> None:
        assert source.validate_payload({}) is False
        assert source.validate_payload({"foo": "bar"}) is False

    # -- normalize --
    def test_normalize_title(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Unprotected port on EC2 instance i-abc123 is being probed"

    def test_normalize_severity(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.HIGH

    def test_normalize_occurred_at(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.month == 1
        assert alert.occurred_at.day == 15

    def test_normalize_source_name(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.source_name == "guardduty"

    def test_normalize_tags(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert "Recon" in alert.tags

    # -- extract_indicators --
    def test_extract_indicators(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "198.51.100.77") in tv

    def test_extract_indicators_empty_on_bad_payload(self, source: GuardDutySource) -> None:
        assert source.extract_indicators({}) == []

    # -- extract_detection_rule_ref --
    def test_extract_detection_rule_ref(self, source: GuardDutySource, payload: dict) -> None:  # type: ignore[type-arg]
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "Recon:EC2/PortProbeUnprotectedPort"

    def test_extract_detection_rule_ref_none_when_missing(
        self, source: GuardDutySource
    ) -> None:
        assert source.extract_detection_rule_ref({}) is None

    # -- verify_webhook_signature --
    def test_verify_signature_true_when_no_secret(
        self, source: GuardDutySource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"body") is True

    def test_verify_signature_false_when_header_missing(
        self, source: GuardDutySource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_secret(monkeypatch, "mysecret")
        assert source.verify_webhook_signature({}, b"body") is False

    def test_verify_signature_valid(
        self, source: GuardDutySource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "mysecret"
        body = b'{"test": true}'
        _setattr_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature({"X-GuardDuty-Signature": sig}, body) is True

    def test_verify_signature_invalid(
        self, source: GuardDutySource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_secret(monkeypatch, "mysecret")
        assert source.verify_webhook_signature(
            {"X-GuardDuty-Signature": "wrong-sig"}, b"body"
        ) is False
```

### Test Pattern Summary

Every source plugin test file follows this structure:

| Test | What it verifies |
|---|---|
| `test_source_name` | Class attribute matches expected string |
| `test_validate_payload_valid` | Returns `True` for realistic fixture |
| `test_validate_payload_invalid` | Returns `False` for empty dict and garbage |
| `test_normalize_title` | Title field correctly extracted |
| `test_normalize_severity` | Severity mapped to correct `AlertSeverity` value |
| `test_normalize_occurred_at` | Timestamp parsed correctly (timezone-aware) |
| `test_normalize_source_name` | `source_name` set to `self.source_name` |
| `test_normalize_tags` | Tags extracted from source-specific fields |
| `test_extract_indicators` | All expected IOCs found with correct types |
| `test_extract_detection_rule_ref` | Rule reference extracted (or `None`) |
| `test_verify_signature_*` | True when no secret, false when header missing, true when valid, false when invalid |

---

## Step 9: Run Tests and Lint

```bash
# Run only your source tests
pytest tests/test_guardduty_source.py -v

# Run all source tests
pytest tests/test_source_integrations.py tests/test_source_registry.py -v

# Full quality checks
make lint       # ruff
make typecheck  # mypy
make test       # all tests
```

---

## Complete Checklist

1. [ ] Create `docs/integrations/guardduty/api_notes.md` with field mapping research
2. [ ] Add webhook secret env var to `app/config.py` (if applicable)
3. [ ] Create `app/integrations/sources/guardduty.py` implementing `AlertSourceBase`
4. [ ] Register in `app/integrations/sources/__init__.py`
5. [ ] Create `tests/fixtures/guardduty_finding.json` with a realistic payload
6. [ ] Create `tests/test_guardduty_source.py` with full test coverage
7. [ ] Run `make lint`, `make typecheck`, `make test` -- all pass

---

## Common Pitfalls

### 1. Raising exceptions in validate_payload or extract_indicators

These methods must never raise. Wrap the body in `try/except Exception: return False` (or empty list). The ingest pipeline depends on this contract.

### 2. Forgetting `source_name = self.source_name` in normalize

The returned `CalsetaAlert` must have `source_name` set. If you forget, the alert will have a `None` or default source name and downstream filtering will break.

### 3. Using `==` instead of `hmac.compare_digest()`

String comparison with `==` is vulnerable to timing attacks. Always use `hmac.compare_digest()` for signature verification, even for bearer token comparisons (see Splunk source for that pattern).

### 4. Not handling both EventBridge wrapper and direct payload formats

Many AWS services wrap the actual data in a `detail` key when sent via EventBridge. Handle both `raw.get("detail", raw)` patterns.

### 5. Timezone-naive datetimes

`CalsetaAlert.occurred_at` must be timezone-aware. Always use `.astimezone()`, `UTC`, or explicit timezone info. A naive datetime will fail Pydantic validation or cause issues downstream.

### 6. Duplicate source_name registration

Each `source_name` must be globally unique. The registry raises `ValueError` if you try to register a duplicate. Choose a distinctive lowercase name.

### 7. Modifying route handlers

You should **not** need to touch `app/api/v1/ingest.py` or `app/api/v1/router.py`. The dynamic `{source_name}` path parameter and registry lookup handle everything.

---

## Reference: Existing Source Plugins

| File | Source | Webhook Signature | Detection Rule Ref |
|---|---|---|---|
| `app/integrations/sources/sentinel.py` | Microsoft Sentinel | HMAC-SHA256 (`X-Sentinel-Signature`) | ARM rule ID (last UUID segment) |
| `app/integrations/sources/elastic.py` | Elastic Security | HMAC-SHA256 (`X-Elastic-Signature`) | `kibana.alert.rule.uuid` |
| `app/integrations/sources/splunk.py` | Splunk | Bearer token (`X-Splunk-Webhook-Secret`) | `rule_name` or `search_name` |
| `app/integrations/sources/generic.py` | Generic Webhook | None (default base) | `rule_id` or `rule_name` |

---

## Reference: CalsetaAlert Schema

```python
class CalsetaAlert(BaseModel):
    # Required
    title: str
    severity: AlertSeverity        # Pending, Informational, Low, Medium, High, Critical
    occurred_at: datetime           # Must be timezone-aware
    source_name: str

    # Optional — used by Pass 2 indicator extraction
    src_ip: str | None = None
    dst_ip: str | None = None
    src_hostname: str | None = None
    dst_hostname: str | None = None
    file_hash_md5: str | None = None
    file_hash_sha256: str | None = None
    file_hash_sha1: str | None = None
    actor_email: str | None = None
    actor_username: str | None = None
    dns_query: str | None = None
    http_url: str | None = None
    http_hostname: str | None = None
    email_from: str | None = None
    email_reply_to: str | None = None

    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
```

## Reference: IndicatorExtract Schema

```python
class IndicatorExtract(BaseModel):
    type: IndicatorType  # ip, domain, hash_md5, hash_sha1, hash_sha256, url, email, account
    value: str
    source_field: str | None = None  # For logging — which field this was extracted from
```
