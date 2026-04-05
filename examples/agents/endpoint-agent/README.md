# Endpoint Agent

A specialist agent that investigates endpoint artifacts including host context, process trees, file hashes, and command lines. Determines compromise level and whether host isolation should be proposed to the approval gate.

## What It Does

1. Extracts endpoint context from the alert: hostname, process name, parent process, command line, file hashes
2. Enriches file hash indicators via Calseta enrichment (VirusTotal results)
3. Documents which EDR API calls would provide additional telemetry (CrowdStrike, Defender for Endpoint, SentinelOne)
4. Calls Claude with the endpoint forensics system prompt → assesses compromise and isolation need
5. Posts an invocation result with compromise level and isolation recommendation

## External EDR API Integration

The agent documents API stubs for:

**CrowdStrike Falcon** (`CS_CLIENT_ID`, `CS_CLIENT_SECRET`):
- Device query by hostname
- Process execution events and behaviors

**Microsoft Defender for Endpoint** (`MDE_CLIENT_ID`, `MDE_CLIENT_SECRET`, `ENTRA_TENANT_ID`):
- Machine profile and risk score

**SentinelOne** (`S1_TENANT`, `S1_API_TOKEN`):
- Agent status and threat status

Look for `# TODO: implement API call` comments in `agent.py` — each includes the exact OAuth/auth pattern.

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

## Registration

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "endpoint-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "endpoint",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8104"
  }'
```
