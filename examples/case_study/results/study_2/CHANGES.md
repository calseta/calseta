# Study 2 — Prompt Grounding + Description Field

Changes from Study 1:

## Calseta Agent Improvements
1. **Anti-hallucination grounding** — System prompt now explicitly instructs the agent to ONLY use data provided, never fabricate enrichment results or threat scores
2. **Alert description field** — Agent now receives the full alert description (narrative context from SIEM), which includes critical details like attack patterns, timing, and scope
3. **Description extraction** — Added source-specific extraction from raw_payload as fallback (Sentinel: properties.description, Elastic: rule.description/reason, Splunk: signature/_raw)

## Platform Changes
4. **`description` column added to alerts table** — First-class normalized field, mapped by all source plugins
5. **CalsetaAlert schema updated** — `description: str | None` added as optional field
6. **Source plugin mapping** — All 3 sources (Sentinel, Elastic, Splunk) now extract and normalize description

## Expected Impact
- Improved Completeness scores: agent now has attack pattern details (e.g., "47 failed + 1 successful auth")
- Improved Accuracy scores: anti-hallucination rules prevent fabricated enrichment data
- Reduced identity confusion: description explicitly names the alert subject
- Minimal token impact: description adds ~50-200 tokens per alert
