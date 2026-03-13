# Alert Source Plugin System

## What This Component Does

The alert source plugin system normalizes incoming webhook payloads from heterogeneous security tools (Sentinel, Elastic, Splunk, and arbitrary JSON) into the Calseta agent-native schema (`CalsetaAlert`). Each source plugin validates payloads, extracts indicators of compromise (Pass 1 of the 3-pass extraction pipeline), optionally associates detection rules, and verifies webhook signatures. The plugin registry resolves the correct plugin by `source_name` at ingest time.

## Interfaces

### AlertSourceBase (`base.py`)

Abstract base class. Every source plugin must subclass and implement:

```python
class AlertSourceBase(ABC):
    source_name: str       # e.g. "sentinel" — used in route path /v1/ingest/{source_name}
    display_name: str      # e.g. "Microsoft Sentinel" — API responses and logs

    # --- Required (abstract) ---
    def validate_payload(self, raw: dict) -> bool: ...
    def normalize(self, raw: dict) -> CalsetaAlert: ...
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]: ...

    # --- Optional (safe defaults) ---
    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # default: None
    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:  # default: True + warning
```

**Contracts callers must uphold:**

- `validate_payload()` must never raise. Return `False` on any error.
- `normalize()` must set `source_name` on the returned `CalsetaAlert` to `self.source_name`. Source-specific fields that don't map are preserved in `raw_payload` by the ingest service layer -- this method must not try to capture them.
- `extract_indicators()` must never raise. Return empty list on failure. This is Pass 1 only.
- `verify_webhook_signature()` must use `hmac.compare_digest()` for signature comparison, never `==`.

### SourceRegistry (`registry.py`)

Module-level singleton: `source_registry`.

```python
source_registry.register(MySource())   # raises ValueError on duplicate source_name
source_registry.get("sentinel")        # returns AlertSourceBase | None
source_registry.list_all()             # returns list[AlertSourceBase]
```

Thread-safe for reads after startup. No dynamic registration at runtime.

### Registration (`__init__.py`)

All built-in sources are imported and registered at package import time:

```python
source_registry.register(SentinelSource())
source_registry.register(ElasticSource())
source_registry.register(SplunkSource())
source_registry.register(GenericSource())
```

### Inputs / Outputs

| Caller | Method | Input | Output |
|---|---|---|---|
| Ingest route | `verify_webhook_signature()` | HTTP headers + raw body bytes | `bool` |
| Ingest route | `validate_payload()` | Parsed JSON dict | `bool` |
| `AlertIngestionService` | `normalize()` | Raw payload dict | `CalsetaAlert` |
| `AlertIngestionService` | `extract_indicators()` | Raw payload dict | `list[IndicatorExtract]` |
| `AlertIngestionService` | `extract_detection_rule_ref()` | Raw payload dict | `str \| None` |

## Key Design Decisions

1. **No-raise contracts for all public methods.** Every method in AlertSourceBase is designed to never raise exceptions that propagate to callers. `validate_payload()` returns `False`, `extract_indicators()` returns `[]`, `verify_webhook_signature()` returns `True` (with a warning log). This isolates source-specific bugs from the ingest pipeline.

2. **Flat dot-notation support for Elastic.** Elastic Kibana connectors send alert fields as flat keys (`"kibana.alert.rule.name": "..."`) not nested JSON. The `_get()` helper in `elastic.py` tries flat-key lookup first, then nested traversal. This dual-path approach was chosen over pre-normalizing the payload to avoid data loss on round-trip.

3. **Splunk bearer-token auth instead of HMAC.** Splunk does not natively support HMAC-signed webhooks. `SplunkSource.verify_webhook_signature()` compares a bearer token from `X-Splunk-Webhook-Secret` using `hmac.compare_digest()` to prevent timing attacks. The body bytes parameter is unused but required by the interface.

4. **Generic source as catch-all.** `GenericSource` accepts any JSON with a `title` field. It supports both explicit `indicators: [{type, value}]` arrays and common field name auto-extraction (`src_ip`, `dest_ip`, `domain`, etc.). This eliminates the need for a custom plugin for one-off integrations.

5. **Severity mapping is per-source.** Each source has its own `_SEVERITY_MAP` because source naming conventions differ (Sentinel uses TitleCase, Elastic uses lowercase, Splunk uses "urgency"). All maps resolve to the shared `AlertSeverity` enum.

## Extension Pattern: Adding a New Source (e.g. GuardDuty)

1. **Create `app/integrations/sources/guardduty.py`**:
   ```python
   from app.integrations.sources.base import AlertSourceBase
   from app.schemas.alert import AlertSeverity, CalsetaAlert
   from app.schemas.indicators import IndicatorExtract, IndicatorType

   class GuardDutySource(AlertSourceBase):
       source_name = "guardduty"
       display_name = "AWS GuardDuty"

       def validate_payload(self, raw: dict) -> bool:
           try:
               return bool(raw.get("detail", {}).get("type"))
           except Exception:
               return False

       def normalize(self, raw: dict) -> CalsetaAlert:
           # Map GuardDuty fields to CalsetaAlert
           ...

       def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:
           # Extract IPs, domains, etc. from detail.resource
           ...
   ```

2. **Register in `app/integrations/sources/__init__.py`**:
   ```python
   from app.integrations.sources.guardduty import GuardDutySource
   source_registry.register(GuardDutySource())
   ```

3. **Add webhook signature verification** (optional override):
   ```python
   def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
       secret = settings.GUARDDUTY_WEBHOOK_SECRET
       if not secret:
           return True
       # Use hmac.compare_digest() -- never ==
       ...
   ```

4. **Add API research doc** at `docs/integrations/guardduty/api_notes.md` (mandatory per project conventions).

5. **Add webhook secret setting** to `app/config.py` if needed (e.g. `GUARDDUTY_WEBHOOK_SECRET: str = ""`).

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| Ingest returns 400 "Invalid payload" | `validate_payload()` returned False | Check source-specific validation logic; log the raw payload |
| Indicators missing from alert | `extract_indicators()` silently failed or field names changed | Check source plugin field mappings; Pass 2/3 may still extract via `indicator_field_mappings` |
| 401 on ingest | `verify_webhook_signature()` failed | Check `{SOURCE}_WEBHOOK_SECRET` env var matches the sending system's configured secret |
| Wrong severity on ingested alert | Source severity value not in `_SEVERITY_MAP` | Falls back to `AlertSeverity.PENDING`; add missing mapping to the source's severity dict |
| Timestamps show current time, not event time | Source time field missing or unparseable | Check `occurred_at` extraction in `normalize()`; unparseable timestamps fall back to `datetime.now()` |
| `source_registry.get()` returns None | Source not imported in `__init__.py` | Ensure import and `source_registry.register()` call exist in `__init__.py` |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/test_source_integrations.py` | Validates `normalize()`, `extract_indicators()`, `validate_payload()`, `extract_detection_rule_ref()` for each built-in source with fixture payloads; tests severity mapping edge cases; tests empty/malformed payloads |
| `tests/test_source_registry.py` | Registry duplicate registration raises ValueError; `get()` returns None for unknown source; `list_all()` returns all registered sources |
| `tests/integration/test_ingest.py` | Full ingest pipeline end-to-end: POST to `/v1/ingest/{source_name}`, validates 202 response, checks alert created in DB, enrichment task enqueued |
| `tests/integration/test_sources.py` | CRUD for source_integrations; lists configured sources |
