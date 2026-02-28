---
name: new-alert-source
description: Scaffold a new alert source integration plugin for Calseta AI. Use when adding a new SIEM or security tool as an alert source.
argument-hint: "<source-name> (e.g. crowdstrike, palo-alto)"
allowed-tools: Read, Write, Glob, WebFetch
---

Scaffold a new alert source integration for: **$ARGUMENTS**

Follow these steps exactly:

1. **Research first.** Before writing any code, fetch and read the official API/webhook documentation for $ARGUMENTS. Produce `docs/integrations/$ARGUMENTS/api_notes.md` with:
   - Webhook payload field names and types (the exact JSON shape Calseta will receive)
   - Authentication method for incoming webhooks (shared secret, HMAC signature, etc.)
   - Any relevant alert severity mappings to OCSF severity levels
   - Edge cases and known quirks
   - Available automation endpoints (for future workflow catalog seeding)

2. **Create the plugin file** at `app/integrations/sources/$ARGUMENTS.py` implementing `AlertSourceBase`:
   ```python
   class <SourceName>AlertSource(AlertSourceBase):
       source_name = "$ARGUMENTS"
       display_name = "<Human Readable Name>"

       def validate_payload(self, raw: dict) -> bool: ...
       def normalize(self, raw: dict) -> OCSFSecurityFinding: ...
       def extract_indicators(self, raw: dict) -> list[IndicatorExtract]: ...
       def extract_detection_rule_ref(self, raw: dict) -> str | None: ...
   ```
   - `normalize()` maps source fields to OCSF Security Finding (class_uid: 2001). Unmappable fields go to `ocsf_data.unmapped`.
   - `raw_payload` is always preserved — never discard it.
   - `extract_indicators()` is Pass 1 of the three-pass pipeline; extract what the plugin author knows is present.

3. **Register the plugin** in `app/integrations/sources/__init__.py`.

4. **Add the ingest route** `POST /v1/ingest/$ARGUMENTS` if it does not already exist via dynamic routing.

5. **Write tests** in `tests/integrations/sources/test_$ARGUMENTS.py` covering:
   - A valid payload normalizes correctly to OCSF
   - An invalid payload returns `validate_payload() == False`
   - Indicator extraction returns expected IOC types and values
   - Unknown fields land in `ocsf_data.unmapped`

6. **Update `docs/HOW_TO_ADD_ALERT_SOURCE.md`** if the implementation reveals anything not covered by the existing guide.

Do not implement polling/pull behavior — push/webhook only in v1.
