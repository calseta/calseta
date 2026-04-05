# Threat Intelligence Agent

A specialist agent that assesses the malice of IP, domain, hash, and URL indicators using Calseta's built-in enrichment results and documenting patterns for external TI sources (VirusTotal, GreyNoise, Shodan, OTX, MalwareBazaar).

## What It Does

1. Fetches the alert and filters to threat-intel-relevant indicators (IP, domain, hash, URL)
2. For each indicator not already conclusively enriched in Calseta, fetches enrichment data
3. Documents which external TI API calls would add value (with exact endpoints and auth patterns)
4. Calls Claude to synthesize enrichment data into a malice assessment with confidence scores
5. Posts an invocation result with overall malice verdict

## External TI Integration

The agent includes documented stubs for external APIs. To activate live calls:

| Source | Indicators | Env Var |
|---|---|---|
| VirusTotal | IP, domain, hash, URL | `VIRUSTOTAL_API_KEY` |
| AbuseIPDB | IP | `ABUSEIPDB_API_KEY` |
| GreyNoise | IP | `GREYNOISE_API_KEY` |
| Shodan | IP | `SHODAN_API_KEY` |
| OTX AlienVault | Domain, hash | `OTX_API_KEY` |
| MalwareBazaar | Hash | No auth required |

Look for `# TODO: implement API call` comments in `agent.py` — each stub includes the exact HTTP call pattern.

Optional packages: `pip install virustotal-python greynoise shodan`

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
    "name": "threat-intel-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "threat_intel",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8102"
  }'
```
