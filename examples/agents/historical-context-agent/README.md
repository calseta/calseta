# Historical Context Agent

The simplest specialist agent — uses only the Calseta REST API (no external calls). Retrieves prior alerts for each indicator, fetches their investigation findings, identifies recurrence patterns, and provides a confidence modifier to the lead investigator.

## What It Does

1. Fetches the current alert and its indicators
2. For each indicator value: `GET /v1/alerts?indicator={value}&page_size=10`
3. For source account (if in raw_payload): `GET /v1/alerts?q={account}&page_size=10`
4. Fetches prior findings for each related alert: `GET /v1/alerts/{uuid}/findings`
5. Calls Claude to identify patterns, recurrence type, and prior verdict summary
6. Posts invocation result with pattern classification and confidence modifier for the lead investigator

## No External Dependencies

This agent intentionally uses only Calseta REST API endpoints. It is the fastest agent to deploy and requires no external API keys beyond `CALSETA_AGENT_KEY`.

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

python agent.py --mode queue
python agent.py --mode invocation --invocation-id <uuid>
```

## Output

The agent classifies each alert as one of:
- **Chronic Noise** — same indicator triggering repeatedly, no prior true positive verdicts
- **Escalating Activity** — prior alerts with true positive verdicts, activity increasing
- **First Occurrence** — no history found
- **Sporadic** — occasional hits, no clear pattern
- **Burst** — sudden spike in alerts for this indicator

The confidence modifier (Increases TP confidence / Decreases TP confidence / Neutral) is the primary signal used by the lead investigator.

## Registration

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "historical-context-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "historical_context",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8105"
  }'
```
