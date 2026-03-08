# Calseta -- Example Agents

This directory contains working sample agents that demonstrate how to build AI-powered SOC investigation agents using Calseta as the data platform.

Calseta is **not** an AI SOC product -- it is the data infrastructure layer. These examples show how **your** agents consume the structured, enriched data that Calseta provides.

---

## Prerequisites

### Calseta Running

All examples assume a running Calseta instance:

```bash
# Start Calseta (API, worker, database)
docker compose up -d

# Create your first API key
curl -X POST http://localhost:8000/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "agent-key", "scopes": ["alerts:read", "alerts:write", "agents:read", "agents:write"]}'
# Save the returned key -- it is shown only once
```

### Claude API Key

Both sample agents call Claude for reasoning. You need an [Anthropic API key](https://console.anthropic.com/).

### Python 3.12+

All examples use Python 3.12+ features (type hints, StrEnum, etc.).

---

## Sample Agents

### 1. REST API Agent (`sample_agent_python.py`)

**Pattern:** Webhook receiver + REST API calls + Claude reasoning

This agent demonstrates the most common integration pattern:

1. Register as an agent with Calseta
2. Receive alert webhooks when new enriched alerts arrive
3. Fetch full alert context from the REST API
4. Build a token-efficient prompt and call Claude
5. Post the investigation finding back to the alert

#### Setup

```bash
# Install dependencies (no agent framework required)
pip install httpx anthropic uvicorn starlette

# Set environment variables
export CALSETA_API_URL=http://localhost:8000
export CALSETA_API_KEY=cai_your_key_here
export ANTHROPIC_API_KEY=sk-ant-your_key_here

# Start the agent
python examples/sample_agent_python.py
```

The agent starts a webhook listener on port 9000 (configurable via `AGENT_PORT`).

#### Register with Calseta

After starting the agent, register it with Calseta so it receives alert webhooks:

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer cai_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample-investigation-agent",
    "endpoint_url": "http://localhost:9000/webhook",
    "trigger_on_severities": ["Medium", "High", "Critical"],
    "documentation": "Sample Claude-powered investigation agent"
  }'
```

#### How It Works

```
Calseta Alert Pipeline                    Sample Agent
========================                  ============

Alert ingested
    |
Indicators extracted
    |
Enrichment completed
    |
Agent dispatch triggered ----POST /webhook---->  Receive webhook
                                                    |
                         <---GET /v1/alerts/{uuid}-- Fetch full context
                                                    |
                         <--GET /v1/alerts/{uuid}/-- Fetch playbooks/SOPs
                              context                |
                                                 Build prompt
                                                    |
                                                 Call Claude API
                                                    |
                         <-POST /v1/alerts/{uuid}/-- Post finding
                              findings
```

#### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CALSETA_API_URL` | No | `http://localhost:8000` | Calseta API base URL |
| `CALSETA_API_KEY` | Yes | -- | Calseta API key (starts with `cai_`) |
| `ANTHROPIC_API_KEY` | Yes | -- | Anthropic API key for Claude |
| `AGENT_PORT` | No | `9000` | Port for the webhook listener |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-20250514` | Claude model to use |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

#### Token Optimization

The sample agent demonstrates several token optimization patterns that reduce Claude API costs:

- **Structured prompts over raw dumps:** Alert data is formatted as compact `key=value` pairs, not as raw JSON payloads.
- **Extracted enrichment verdicts:** Only the meaningful fields from enrichment results (verdict, risk_score, country) are included -- not the full provider API response.
- **Context documents inline:** Applicable playbooks and SOPs are included directly in the prompt so Claude can follow them, eliminating back-and-forth tool calls.
- **Concise system prompt:** The system prompt defines the output structure upfront, so Claude does not waste tokens on formatting decisions.

---

### 2. MCP Agent (`sample_agent_mcp.py`)

**Pattern:** MCP client + Claude reasoning (no direct REST API calls)

This agent demonstrates the MCP-native integration pattern, where the agent communicates with Calseta exclusively through the Model Context Protocol server. No direct HTTP calls to the REST API are needed.

The MCP pattern is particularly powerful for agents built with Claude's native tool-use capabilities, as Calseta's MCP resources and tools map directly to Claude's tool interface.

#### Why MCP-Only?

| Advantage | REST API Agent | MCP Agent |
|---|---|---|
| Framework coupling | Must know endpoint paths, pagination, envelopes | Framework-agnostic protocol |
| Data optimization | Returns raw API responses | Returns agent-optimized, token-efficient data |
| Discoverability | Must read API docs | Lists resources and tools at runtime |
| Client compatibility | Custom HTTP client code | Works with any MCP client (Claude Desktop, Cursor, etc.) |

#### Setup

```bash
# Install dependencies
pip install mcp anthropic

# Set environment variables
export CALSETA_MCP_URL=http://localhost:8001/sse
export CALSETA_API_KEY=cai_your_key_here
export ANTHROPIC_API_KEY=sk-ant-your_key_here

# Start the agent
python examples/sample_agent_mcp.py
```

No webhook listener is needed -- the MCP agent proactively reads alerts and investigates.

#### How It Works

```
Calseta MCP Server                         Sample MCP Agent
==================                         ================

                                            Connect via SSE
                    <-- initialize --------  Handshake
                                            |
                    <-- read resource -----  calseta://alerts
                    --- alert list -------->  Select alert
                                            |
                    <-- read resource -----  calseta://alerts/{uuid}
                    --- full context ------>  Parse indicators, enrichment
                                            |
                    <-- read resource -----  calseta://alerts/{uuid}/context
                    --- playbooks/SOPs ---->  Read investigation guidance
                                            |
                    <-- read resource -----  calseta://workflows
                    --- workflow catalog -->  Know available actions
                                            |
                                            Build prompt with all context
                                            |
                                            Call Claude API
                                            |
                    <-- call tool ---------  post_alert_finding
                    --- finding posted ---->  Record analysis
                                            |
                    <-- call tool ---------  execute_workflow
                    --- queued/approved --->  Trigger response action
```

#### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CALSETA_MCP_URL` | No | `http://localhost:8001/sse` | MCP server SSE endpoint |
| `CALSETA_API_KEY` | Yes | -- | Calseta API key (starts with `cai_`) |
| `ANTHROPIC_API_KEY` | Yes | -- | Anthropic API key for Claude |

#### MCP Resources Used

| Resource URI | What It Provides |
|---|---|
| `calseta://alerts` | Recent alerts (last 50) with status, severity, source |
| `calseta://alerts/{uuid}` | Full alert with indicators, enrichment, detection rule, context docs |
| `calseta://alerts/{uuid}/context` | Applicable playbooks and SOPs matched by targeting rules |
| `calseta://alerts/{uuid}/activity` | Audit log of all actions on the alert |
| `calseta://workflows` | Workflow catalog with documentation and configuration |
| `calseta://workflows/{uuid}` | Full workflow detail with code and approval settings |
| `calseta://detection-rules` | Detection rule catalog with MITRE mappings |
| `calseta://enrichments/{type}/{value}` | On-demand indicator enrichment (cache-first) |
| `calseta://metrics/summary` | SOC health metrics (last 30 days) |

#### MCP Tools Used

| Tool | What It Does |
|---|---|
| `post_alert_finding` | Attach an agent analysis finding to an alert |
| `update_alert_status` | Change alert status (Open, Triaging, Escalated, Closed) |
| `execute_workflow` | Trigger a workflow (may require human approval) |
| `enrich_indicator` | On-demand enrichment against all configured providers |
| `search_alerts` | Search alerts by status, severity, source, time range, tags |
| `search_detection_rules` | Search rules by name, MITRE tactic/technique, source |

#### Extending the MCP Agent

- **Multi-alert correlation:** Use `search_alerts` tool to find related alerts by tags or time window
- **On-demand enrichment:** Use `enrich_indicator` tool for indicators not yet enriched
- **Activity awareness:** Read `calseta://alerts/{uuid}/activity` to check if other agents already investigated
- **Status management:** Use `update_alert_status` tool to move alerts through the triage pipeline
- **Metrics context:** Read `calseta://metrics/summary` to understand current SOC health before triaging

---

## Design Philosophy

Both sample agents follow the same principles that Calseta is built on:

### Calseta Does the Data Work, Your Agent Does the Reasoning

Calseta handles: normalization, enrichment, indicator extraction, context matching, deduplication. Your agent receives clean, structured, enriched data and focuses entirely on investigation logic.

### Token Efficiency is First-Class

Every API response and webhook payload is designed to give agents exactly what they need. The `raw` enrichment responses are stripped from webhook payloads and API responses (unless specifically requested). The `_metadata` block tells the agent what data is available without having to inspect every field.

### Framework Agnosticism

These examples use raw `httpx` + `anthropic` SDK. No LangChain, no CrewAI, no framework lock-in. The same patterns work with any framework or no framework at all. Calseta's REST API and MCP server are the integration points.

### Graceful Degradation

Both agents handle missing data gracefully. If enrichment fails, the agent notes it and adjusts confidence. If context documents are unavailable, the agent proceeds without them. If the Claude API call fails, the error is logged without crashing.

---

## Extending These Examples

These are starting points. Production agents will typically add:

- **Task queue:** Move investigation work out of the webhook request handler into a durable task queue (Redis, SQS, etc.)
- **Workflow execution:** Call `POST /v1/workflows/{uuid}/execute` to trigger automated response actions when investigation reveals a confirmed threat
- **Alert status updates:** Call `PATCH /v1/alerts/{uuid}` to move alerts through the triage lifecycle (Open -> Triaging -> Escalated -> Closed)
- **Multi-model routing:** Use a fast model for initial triage and a capable model for deep investigation
- **Feedback loops:** Track which findings lead to true positives vs. false positives and use that data to improve prompts

---

## Troubleshooting

### Agent not receiving webhooks

1. Verify the agent is registered: `curl http://localhost:8000/v1/agents -H "Authorization: Bearer cai_..."`
2. Test webhook delivery: `curl -X POST http://localhost:8000/v1/agents/{uuid}/test -H "Authorization: Bearer cai_..."`
3. Check the agent's health endpoint: `curl http://localhost:9000/health`
4. Verify `trigger_on_severities` and `trigger_on_sources` match the alerts being ingested

### Claude API errors

- `401`: Check `ANTHROPIC_API_KEY` is set correctly
- `429`: Rate limited -- the agent does not implement retry/backoff on Claude calls (add this for production)
- `529`: Anthropic API overloaded -- retry with exponential backoff

### Finding not posted

- Verify `CALSETA_API_KEY` has `alerts:write` scope
- Check the agent logs for HTTP error details
- Verify the alert UUID exists: `curl http://localhost:8000/v1/alerts/{uuid} -H "Authorization: Bearer cai_..."`

### MCP agent cannot connect

- Verify the MCP server is running: `curl http://localhost:8001/sse` should start an SSE stream
- Check the MCP server logs for authentication failures: `docker compose logs mcp`
- Verify `CALSETA_API_KEY` is a valid API key with appropriate scopes (`alerts:read`, `alerts:write`, `workflows:execute`, `enrichments:read`)
- If using a non-default URL, ensure `CALSETA_MCP_URL` includes the `/sse` path

### MCP resource returns empty data

- Verify alerts have been ingested: `curl http://localhost:8000/v1/alerts -H "Authorization: Bearer cai_..."`
- For enrichment data, verify enrichment providers are configured (check environment variables for `VIRUSTOTAL_API_KEY`, `ABUSEIPDB_API_KEY`, etc.)
- For context documents, verify at least one document exists and has targeting rules that match the alert
