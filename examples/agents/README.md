# Calseta Live Agent

End-to-end investigation test that runs a real LLM against a live Calseta instance.
Tests both pull (REST/MCP) and push (webhook) agent patterns.

## Quick Start

```bash
# 1. Start Calseta with seeded lab data
make lab

# 2. Load env vars from your .env file
set -a && source .env && set +a

# 3. Install dependencies (if not already in your venv)
pip install httpx anthropic openai mcp starlette uvicorn

# 4. Run an investigation
python examples/agents/investigate_alert.py --model azure
```

## Modes

| Mode | Description |
|---|---|
| `--mode rest` | Pull: REST API calls to `localhost:8000` (default) |
| `--mode mcp` | Pull: MCP protocol to `localhost:8001` |
| `--register` | Push: registers as webhook agent, listens for alerts |

## Models

| Flag | Description |
|---|---|
| `--model claude` | Claude Sonnet via Anthropic API (default) |
| `--model openai` | GPT-4o via OpenAI API |
| `--model azure` | Azure OpenAI (any deployed model) |

## Test Cases

### 1. Basic pull investigation (REST + Azure OpenAI)

Fetch alerts, pick the highest severity one, analyze, post finding.

```bash
python examples/agents/investigate_alert.py --mode rest --model azure
```

### 2. MCP pull investigation

Same flow but all data reads/writes go through MCP resources and tools.

```bash
python examples/agents/investigate_alert.py --mode mcp --model azure
```

### 3. Investigate a specific alert

```bash
python examples/agents/investigate_alert.py --alert <uuid> --model azure
```

### 4. Investigate all open alerts

```bash
python examples/agents/investigate_alert.py --all --model azure
```

### 5. Investigate with workflow execution

LLM analyzes the alert and recommends a workflow — this flag actually executes it.

```bash
python examples/agents/investigate_alert.py --model azure --execute-workflows
```

### 6. Webhook registration mode (push)

Registers the agent with Calseta, starts a webhook listener, and investigates
alerts automatically as they arrive. Deregisters on Ctrl+C.

```bash
# Basic — listen on port 9000, all alerts
python examples/agents/investigate_alert.py --register --model azure

# Filter to high/critical alerts only
python examples/agents/investigate_alert.py --register --model azure \
  --trigger-severities High,Critical

# Custom port + source filter
python examples/agents/investigate_alert.py --register --model azure \
  --agent-port 9001 --trigger-sources sentinel,elastic

# With workflow execution enabled
python examples/agents/investigate_alert.py --register --model azure \
  --trigger-severities Critical --execute-workflows
```

Then ingest an alert to trigger the webhook:

```bash
curl -X POST http://localhost:8000/v1/alerts/ingest/generic \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test alert for webhook agent",
    "severity": "High",
    "description": "Suspicious login from unknown IP"
  }'
```

### 7. Full matrix test

Run all combinations to validate both data paths and the LLM provider:

```bash
# REST + Azure
python examples/agents/investigate_alert.py --mode rest --model azure --all

# MCP + Azure
python examples/agents/investigate_alert.py --mode mcp --model azure --all

# Webhook + Azure
python examples/agents/investigate_alert.py --register --model azure
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CALSETA_API_KEY` | Yes | Calseta API key (`cai_` prefix) |
| `ANTHROPIC_API_KEY` | For `--model claude` | Anthropic API key |
| `OPENAI_API_KEY` | For `--model openai` | OpenAI API key |
| `AZURE_OPENAI_API_KEY` | For `--model azure` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | For `--model azure` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | For `--model azure` | Azure OpenAI deployment name |
| `AZURE_OPENAI_API_VERSION` | No | Azure API version (default: `2024-12-01-preview`) |
| `CALSETA_API_URL` | No | REST API URL (default: `http://localhost:8000`) |
| `CALSETA_MCP_URL` | No | MCP SSE endpoint (default: `http://localhost:8001/sse`) |

All of these can be set in your `.env` file and loaded with:

```bash
set -a && source .env && set +a
```

## CLI Reference

```
python examples/agents/investigate_alert.py --help
```

| Flag | Default | Description |
|---|---|---|
| `--mode` | `rest` | `rest` or `mcp` |
| `--model` | `claude` | `claude`, `openai`, or `azure` |
| `--alert UUID` | — | Investigate a specific alert |
| `--all` | — | Investigate all open enriched alerts |
| `--execute-workflows` | — | Execute LLM-recommended workflows |
| `--register` | — | Webhook registration mode (push) |
| `--agent-port` | `9000` | Webhook listener port |
| `--trigger-severities` | — | Comma-separated severity filter |
| `--trigger-sources` | — | Comma-separated source filter |
