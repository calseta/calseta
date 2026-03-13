# Calseta -- Example Agents

This directory contains working sample agents that demonstrate how to build AI-powered SOC investigation agents using Calseta as the data platform.

Calseta is **not** an AI SOC product -- it is the data infrastructure layer. These examples show how **your** agents consume the structured, enriched data that Calseta provides.

---

## Prerequisites

### Calseta Running

All examples assume a running Calseta instance:

```bash
# Start Calseta (API, MCP, worker, database)
make lab

# Or manually:
docker compose up -d
```

### API Key

Create an API key (or use the one printed by `make lab`):

```bash
curl -X POST http://localhost:8000/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "agent-key", "scopes": ["alerts:read", "alerts:write", "agents:read", "agents:write", "workflows:read", "workflows:execute", "enrichments:read"]}'
# Save the returned key -- it is shown only once
```

### LLM API Key

At least one of:
- `ANTHROPIC_API_KEY` -- for Claude (default)
- `OPENAI_API_KEY` -- for GPT-4o
- `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` -- for Azure OpenAI

### Python 3.12+

All examples use Python 3.12+ features (type hints, StrEnum, etc.).

---

## Investigation Agent (`agents/investigate_alert.py`)

A full-featured CLI agent that runs real LLM-powered SOC investigations against a live Calseta instance. Supports three data modes, three LLM providers, and both pull and push operation.

### Install

```bash
pip install httpx anthropic openai mcp uvicorn starlette
```

### Quick Start

```bash
export CALSETA_API_KEY=cai_your_key_here
export ANTHROPIC_API_KEY=sk-ant-your_key_here

# Investigate the highest-severity enriched alert via REST API + Claude
python examples/agents/investigate_alert.py

# Same thing via MCP
python examples/agents/investigate_alert.py --mode mcp

# Use OpenAI instead of Claude
python examples/agents/investigate_alert.py --model openai

# Target a specific alert
python examples/agents/investigate_alert.py --alert <uuid>

# Investigate all open enriched alerts
python examples/agents/investigate_alert.py --all

# Execute workflows recommended by the LLM
python examples/agents/investigate_alert.py --execute-workflows

# Register as a webhook agent (push mode) -- listens for alerts from Calseta
python examples/agents/investigate_alert.py --register

# Register with custom port and severity filter
python examples/agents/investigate_alert.py --register --agent-port 9000 \
  --trigger-severities High,Critical
```

### Modes

| Mode | Flag | Transport | Description |
|---|---|---|---|
| REST (pull) | `--mode rest` | HTTP to port 8000 | Direct REST API calls. Default. |
| MCP (pull) | `--mode mcp` | SSE to port 8001 | MCP protocol -- framework-agnostic, agent-optimized data. |
| Webhook (push) | `--register` | HTTP listener | Registers with Calseta, receives alert webhooks, investigates on arrival. |

### LLM Providers

| Provider | Flag | Env Var |
|---|---|---|
| Claude | `--model claude` (default) | `ANTHROPIC_API_KEY` |
| OpenAI GPT-4o | `--model openai` | `OPENAI_API_KEY` |
| Azure OpenAI | `--model azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |

### What It Does

1. Creates a short-lived agent-type API key (scoped to investigation)
2. Lists alerts and selects one (or uses `--alert UUID`)
3. Fetches full alert context: indicators, enrichment, detection rule, runbooks
4. Builds a token-efficient prompt and calls the LLM
5. Posts the investigation finding back to the alert
6. Optionally executes suggested workflows (`--execute-workflows`)
7. Revokes the agent API key on exit

### How It Works (Pull Mode)

```
Calseta                                   Live Agent
=======                                   ==========

                                          Create agent API key
                                          |
              <-- list alerts ----------  GET /v1/alerts (or calseta://alerts)
              --- alert list ---------->  Select alert
                                          |
              <-- get alert -----------  GET /v1/alerts/{uuid}
              --- full context -------->  Parse indicators, enrichment
                                          |
              <-- get context ---------  GET /v1/alerts/{uuid}/context
              --- playbooks/SOPs ------>  Read investigation guidance
                                          |
              <-- get workflows -------  GET /v1/workflows
              --- workflow catalog ---->  Know available actions
                                          |
                                          Build prompt + call LLM
                                          |
              <-- post finding --------  POST /v1/alerts/{uuid}/findings
                                          |
              <-- execute workflow -----  POST /v1/workflows/{uuid}/execute
                                          |
                                          Revoke agent API key
```

### How It Works (Webhook/Push Mode)

```
Calseta Alert Pipeline                    Live Agent (--register)
======================                    ========================

                                          Register as agent
                                          Start webhook listener (:9000)
Alert ingested                            |
    |                                     |
Indicators extracted                      |
    |                                     |
Enrichment completed                      |
    |                                     |
Agent dispatch triggered --POST /webhook-->  Receive webhook
                                             |
                         <--GET /v1/alerts/-- Fetch full context
                              {uuid}         |
                                             Build prompt + call LLM
                                             |
                         <--POST findings --- Post finding
                                             |
                                          Deregister + revoke key on Ctrl+C
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CALSETA_API_URL` | No | `http://localhost:8000` | Calseta REST API base URL |
| `CALSETA_MCP_URL` | No | `http://localhost:8001/sse` | Calseta MCP SSE endpoint |
| `CALSETA_API_KEY` | Yes | -- | Calseta API key (`cai_` prefix) |
| `ANTHROPIC_API_KEY` | For `--model claude` | -- | Anthropic API key |
| `OPENAI_API_KEY` | For `--model openai` | -- | OpenAI API key |
| `AZURE_OPENAI_API_KEY` | For `--model azure` | -- | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | For `--model azure` | -- | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | For `--model azure` | -- | Azure OpenAI deployment name |

### CLI Reference

```
python examples/agents/investigate_alert.py --help
```

| Flag | Description |
|---|---|
| `--mode rest\|mcp` | Data source (default: `rest`) |
| `--model claude\|openai\|azure` | LLM provider (default: `claude`) |
| `--alert UUID` | Investigate a specific alert |
| `--all` | Investigate all open enriched alerts |
| `--execute-workflows` | Execute LLM-recommended workflows |
| `--register` | Webhook registration mode (push) |
| `--agent-port PORT` | Webhook listener port (default: 9000) |
| `--trigger-severities X,Y` | Severity filter for webhooks |
| `--trigger-sources X,Y` | Source filter for webhooks |

---

## Case Study (`case_study/`)

A before-and-after comparison showing the difference between a naive agent (raw API dumps, no enrichment) and a Calseta-powered agent (structured, enriched, context-rich data).

See `case_study/README.md` for details.

---

## Design Philosophy

### Calseta Does the Data Work, Your Agent Does the Reasoning

Calseta handles: normalization, enrichment, indicator extraction, context matching, deduplication. Your agent receives clean, structured, enriched data and focuses entirely on investigation logic.

### Token Efficiency is First-Class

Every API response and MCP resource is designed to give agents exactly what they need. The `raw` enrichment responses are stripped from default responses. The `_metadata` block tells the agent what data is available without inspecting every field.

### Framework Agnosticism

These examples use raw `httpx` + `anthropic`/`openai` SDKs. No LangChain, no CrewAI, no framework lock-in. The same patterns work with any framework or no framework at all. Calseta's REST API and MCP server are the integration points.

### Graceful Degradation

The agent handles missing data gracefully. If enrichment fails, it notes it and adjusts confidence. If context documents are unavailable, it proceeds without them. If the LLM call fails, the error is logged without crashing.

---

## MCP Resources

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

## MCP Tools

| Tool | What It Does |
|---|---|
| `post_alert_finding` | Attach an agent analysis finding to an alert |
| `update_alert_status` | Change alert status (Open, Triaging, Escalated, Closed) |
| `execute_workflow` | Trigger a workflow (may require human approval) |
| `enrich_indicator` | On-demand enrichment against all configured providers |
| `search_alerts` | Search alerts by status, severity, source, time range, tags |
| `search_detection_rules` | Search rules by name, MITRE tactic/technique, source |

---

## Troubleshooting

### Agent not receiving webhooks (--register mode)

1. Verify the agent registered: check the startup log for `Agent registered: <uuid>`
2. Test webhook delivery: `curl -X POST http://localhost:8000/v1/agents/{uuid}/test -H "Authorization: Bearer cai_..."`
3. Check the agent's health endpoint: `curl http://localhost:9000/health`
4. Verify `--trigger-severities` and `--trigger-sources` match the alerts being ingested

### LLM API errors

- `401`: Check `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is set correctly
- `429`: Rate limited -- add retry/backoff for production use
- `529`: Anthropic API overloaded -- retry with exponential backoff

### Finding not posted

- Verify `CALSETA_API_KEY` has `alerts:write` scope
- Check the agent logs for HTTP error details
- Verify the alert UUID exists: `curl http://localhost:8000/v1/alerts/{uuid} -H "Authorization: Bearer cai_..."`

### MCP connection issues (--mode mcp)

- Verify the MCP server is running: `curl http://localhost:8001/sse` should start an SSE stream
- Check the MCP server logs: `docker compose logs mcp`
- Verify `CALSETA_API_KEY` has appropriate scopes
- Ensure `CALSETA_MCP_URL` includes the `/sse` path
