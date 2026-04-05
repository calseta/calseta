# Calseta Reference Agents

Working reference implementations for the Calseta Phase 7 multi-agent investigation system. These are complete, runnable examples you can fork and adapt — not production templates.

**What these are:** Demonstrating how to connect external AI agents to Calseta's agent control plane (alert queue, invocation system, action approval gate).

**What these are not:** Production-hardened code. You will want to add retry logic, observability, dead letter handling, and deploy them behind a proper service layer before putting them in front of real alerts.

---

## Architecture

```
                         ┌─────────────────────────┐
                         │     Calseta Platform     │
                         │   /v1/queue              │
                         │   /v1/invocations        │
                         │   /v1/alerts/{}/findings │
                         │   /v1/actions            │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │    lead-investigator     │
                         │    (orchestrator)        │
                         └──┬───┬───┬───┬──────────┘
                            │   │   │   │ (parallel delegation)
              ┌─────────────┘   │   │   └──────────────────┐
              │                 │   │                       │
   ┌──────────▼──────┐  ┌───────▼──┐ ┌───────────────┐  ┌──▼──────────────────┐
   │ threat-intel-   │  │ identity-│ │ endpoint-     │  │ historical-context- │
   │ agent           │  │ agent    │ │ agent         │  │ agent               │
   └─────────────────┘  └──────────┘ └───────────────┘  └─────────────────────┘
              │                               │
              └──────────────┬────────────────┘
                             │ (results back to lead-investigator)
                    ┌────────▼────────┐
                    │ lead-investigator│
                    │ LLM synthesis   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ response-agent  │
                    │ (optional next  │
                    │  invocation)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ /v1/actions     │
                    │ (approval gate) │
                    └─────────────────┘
```

---

## Quick Start: Lead Investigator + Specialists

### 1. Start Calseta

```bash
make lab
```

### 2. Create an agent API key

```bash
curl -X POST http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "phase7-agents", "scopes": ["alerts:read", "alerts:write", "agents:read", "agents:write"]}'
```

### 3. Register the specialists

```bash
# Register each specialist and capture their UUIDs
THREAT_INTEL_UUID=$(curl -s -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "threat-intel-agent", "execution_mode": "external", "agent_type": "specialist", "role": "threat_intel", "adapter_type": "http", "endpoint_url": "http://localhost:8102"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['uuid'])")

IDENTITY_UUID=$(curl -s -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "identity-agent", "execution_mode": "external", "agent_type": "specialist", "role": "identity", "adapter_type": "http", "endpoint_url": "http://localhost:8103"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['uuid'])")

ENDPOINT_UUID=$(curl -s -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "endpoint-agent", "execution_mode": "external", "agent_type": "specialist", "role": "endpoint", "adapter_type": "http", "endpoint_url": "http://localhost:8104"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['uuid'])")

HISTORICAL_UUID=$(curl -s -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "historical-context-agent", "execution_mode": "external", "agent_type": "specialist", "role": "historical_context", "adapter_type": "http", "endpoint_url": "http://localhost:8105"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['uuid'])")
```

### 4. Install dependencies and run

```bash
# Install dependencies (all agents share the same requirements)
pip install httpx anthropic

# Set env vars
export CALSETA_API_URL=http://localhost:8000
export CALSETA_AGENT_KEY=cak_your_key
export ANTHROPIC_API_KEY=sk-ant-...
export THREAT_INTEL_AGENT_UUID=$THREAT_INTEL_UUID
export IDENTITY_AGENT_UUID=$IDENTITY_UUID
export ENDPOINT_AGENT_UUID=$ENDPOINT_UUID
export HISTORICAL_CONTEXT_AGENT_UUID=$HISTORICAL_UUID

# Run lead investigator (processes next alert from queue)
python examples/agents/lead-investigator/agent.py --mode queue
```

---

## Agent Reference

| Agent | Role | Mode | External APIs |
|---|---|---|---|
| [lead-investigator](lead-investigator/) | Orchestrator — delegates, synthesizes, posts finding | orchestrator | Anthropic only |
| [siem-query-agent](siem-query-agent/) | Generates KQL/SPL/EQL queries for investigation timelines | specialist | Anthropic only |
| [threat-intel-agent](threat-intel-agent/) | IOC malice assessment via enrichment + TI sources | specialist | VirusTotal, GreyNoise, Shodan, OTX (stubs) |
| [identity-agent](identity-agent/) | Account compromise risk assessment | specialist | Microsoft Graph, Okta (stubs) |
| [endpoint-agent](endpoint-agent/) | Process tree, hash, LOLBin, C2 pattern analysis | specialist | CrowdStrike, MDE, SentinelOne (stubs) |
| [historical-context-agent](historical-context-agent/) | Alert recurrence + prior verdict pattern analysis | specialist | None — Calseta REST API only |
| [response-agent](response-agent/) | Prioritized response actions with confidence scores + approval gate submission | specialist | Anthropic only |

---

## How to Fork

Each agent is a single `agent.py` file with three customization points:

1. **`system_prompt.md`** — change the analyst persona, thresholds, and output format without touching code
2. **`# TODO: implement API call` stubs** — each external integration is a documented stub with exact endpoints and auth patterns. Uncomment and implement to add live data.
3. **`select_specialists()` in lead-investigator** — rule-based routing logic. Modify to add new specialists or change routing rules.

Everything else (queue polling, invocation handling, finding posting) is boilerplate that you should keep as-is.

### Adding a new specialist

1. Copy the `historical-context-agent/` directory (simplest agent — no external deps)
2. Update `system_prompt.md` for your domain
3. Replace the history-fetching logic in `agent.py` with your logic
4. Register it in Calseta and add its UUID to `lead-investigator`'s env vars
5. Add a routing rule in `lead-investigator/agent.py:select_specialists()`

---

## Legacy: v1 Standalone Agent (no control plane)

The original pre-Phase 7 agent is at `examples/agents/investigate_alert.py`. It runs standalone against the Calseta REST API or MCP server and does not use the agent control plane (queue, invocations, delegation). It supports multiple LLM providers (Claude, OpenAI, Azure OpenAI) and is useful for testing a live Calseta instance without setting up the full multi-agent system.

See the [original README](../README.md) for usage.
