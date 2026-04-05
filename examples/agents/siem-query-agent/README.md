# SIEM Query Agent

A specialist agent that generates ready-to-run SIEM queries (KQL for Sentinel, SPL for Splunk, EQL for Elastic) based on Calseta alert context. Primarily invoked by the lead-investigator orchestrator but can also run standalone against the alert queue.

## What It Does

1. Loads alert context: source SIEM, indicators, time window
2. Selects query language based on `source_name` (Sentinel → KQL, Splunk → SPL, Elastic → EQL)
3. Calls Claude with the SIEM analyst system prompt → generates 2-3 targeted queries
4. Posts the queries as an invocation result (when invoked by orchestrator) or prints to stdout (queue mode)

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CALSETA_API_URL` | No | Calseta API base URL (default: `http://localhost:8000`) |
| `CALSETA_AGENT_KEY` | Yes | Agent API key (`cak_` prefix) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |

## Quick Start

```bash
pip install -r requirements.txt

export CALSETA_AGENT_KEY=cak_your_key_here
export ANTHROPIC_API_KEY=sk-ant-...

# Process next alert from queue
python agent.py --mode queue

# Handle a delegated invocation
python agent.py --mode invocation --invocation-id <uuid>
```

## Query Language Mapping

| Calseta source_name | Query Language |
|---|---|
| `sentinel`, `microsoft_sentinel` | KQL |
| `splunk` | SPL |
| `elastic`, `elastic_security` | EQL |
| `generic` (default) | KQL |

## Registration

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "siem-query-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "siem_query",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8101"
  }'
```
