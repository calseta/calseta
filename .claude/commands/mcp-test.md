---
name: mcp-test
description: Test the Calseta MCP server interactively. Use when verifying MCP resources and tools work correctly against a running local instance.
allowed-tools: Bash, Read
---

Run an end-to-end test of the Calseta MCP server.

**Prerequisite check:** Verify `docker compose up` is running before proceeding.

```bash
curl -s http://localhost:8000/health
```

If that fails, stop and tell the user the stack isn't running.

**Test sequence — work through each MCP resource and tool:**

1. **List alerts** — read `calseta://alerts` and confirm response structure matches the PRD Section 7.8 envelope format
2. **List detection rules** — read `calseta://detection-rules`
3. **List workflows** — read `calseta://workflows`
4. **Metrics summary** — read `calseta://metrics/summary` and verify all expected keys are present (`period`, `alerts`, `workflows`)
5. **On-demand enrichment** — call `enrich_indicator` tool with a test IP (e.g., `8.8.8.8`) and confirm response structure
6. **Post a finding** — call `post_alert_finding` on an existing alert UUID from step 1 with a test payload; confirm 201 response
7. **Search** — call `search_alerts` with a severity filter; confirm results

For each test, report:
- Whether the resource/tool responded correctly
- The exact response shape received
- Any field mismatches vs. the PRD spec in Section 7.8

Summarize findings in a table: Resource/Tool | Status | Notes
