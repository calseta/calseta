# Study 3 — Skip Enrichment for Non-Routable Indicators

Changes from Study 2:

## Problem

In Study 2, Scenario 3 (Anomalous Data Transfer) was the one case where Calseta clearly underperformed: **7.2 vs Naive's 9.0** (-1.78 quality gap). Root cause: Calseta enriched the internal IP `10.0.8.55` (RFC 1918) through VirusTotal/AbuseIPDB, which returned fabricated "Malicious/TOR" verdicts for a private address. The agent then reported the internal file server as an external threat. The LLM judge flagged: *"The source IP 10.0.8.55 was inaccurately described as external and associated with TOR, which is incorrect."*

## Platform Changes

1. **New module: `app/services/indicator_validation.py`** — Pure-function validation that checks whether an indicator is worth sending to external enrichment providers
   - IPs: uses Python `ipaddress.is_global` — rejects RFC 1918, loopback, link-local, CGNAT, multicast, reserved, unspecified (IPv4 and IPv6)
   - Domains: rejects `.internal`, `.local`, `.localhost`, `.home`, `.lan`, `.corp`, `.test`, `.example`, `.invalid`, `.arpa` suffixes
   - URLs: extracts hostname and delegates to IP or domain validator
   - Hashes, emails, accounts: always enrichable (no filtering)

2. **Guard added to `EnrichmentService.enrich_indicator()`** — Single chokepoint for all enrichment paths (worker pipeline, on-demand endpoint, MCP tool). Non-enrichable indicators return a `_validation` skipped result instead of calling external APIs

3. **Indicators still persisted** — Only external API enrichment is skipped. The indicator record and its `_validation` skip reason are stored in `enrichment_results` JSONB, so agents see why enrichment was skipped

## What the Agent Sees (Before vs After)

**Before (Study 2):**
```json
{
  "virustotal": {"success": true, "extracted": {"malice": "Malicious", "tor_exit_node": true}},
  "abuseipdb": {"success": true, "extracted": {"malice": "Malicious", "abuse_confidence": 100}}
}
```
Agent concludes: "10.0.8.55 is a confirmed TOR exit node with maximum abuse score" (wrong).

**After (Study 3):**
```json
{
  "_validation": {"success": false, "status": "skipped", "error_message": "Enrichment skipped: non-routable IP address (10.0.8.55)"}
}
```
Agent concludes: "10.0.8.55 is an internal server; focus investigation on the destination and data volume" (correct).

## Expected Impact

- **Scenario 3 quality**: ~7.2 → ~8.5–9.2 (eliminates the primary accuracy penalty)
- **Overall Calseta average**: +0.3 points (1/5 scenarios improved)
- **Narrative**: eliminates the only scenario where Calseta was clearly worse than Naive
- **No regression risk**: other scenarios have no private IPs in indicator sets; public IPs are unaffected

## Files Changed

| File | Change |
|------|--------|
| `app/services/indicator_validation.py` | **New** — enrichability validation functions |
| `app/services/enrichment.py` | **Edit** — added validation guard in `enrich_indicator()` |
| `tests/unit/services/test_indicator_validation.py` | **New** — 45 unit tests |
| `tests/test_enrichment_service.py` | **Edit** — 2 integration tests added |
