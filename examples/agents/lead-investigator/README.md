# Lead Investigator Agent

The lead investigator is the orchestrator in the Calseta Phase 7 multi-agent investigation system. It checks out alerts from the queue, selects the appropriate specialist sub-agents based on alert indicators (rule-based, no LLM), delegates to them in parallel, waits for their findings, and synthesizes everything into a final verdict using Claude.

## How It Works

1. Check out an alert from `GET /v1/queue` (queue mode) or load from an invocation (invocation mode)
2. Fetch full alert detail including indicators and enrichment results
3. Rule-based specialist selection:
   - IP, domain, hash, or URL indicators → threat-intel-agent
   - Account or email indicators → identity-agent
   - Host or process context in raw_payload → endpoint-agent
   - Always → historical-context-agent
4. Delegate all selected specialists in parallel via `POST /v1/invocations/parallel`
5. Poll each invocation via `GET /v1/invocations/{uuid}/poll` (30s timeout each)
6. Call Claude with system prompt + all specialist findings → synthesize verdict
7. Post finding via `POST /v1/alerts/{uuid}/findings`
8. If LLM recommends containment actions, post via `POST /v1/actions`

## Registration

Register this agent with Calseta before running:

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer $CALSETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "lead-investigator",
    "execution_mode": "external",
    "agent_type": "orchestrator",
    "role": "investigation",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8100",
    "trigger_on_severities": ["High", "Critical"]
  }'
```

Save the returned agent UUID — you will need it if other orchestrators delegate to this agent.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CALSETA_API_URL` | No | Calseta API base URL (default: `http://localhost:8000`) |
| `CALSETA_AGENT_KEY` | Yes | Agent API key (`cak_` prefix) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `THREAT_INTEL_AGENT_UUID` | Recommended | UUID of registered threat-intel-agent |
| `IDENTITY_AGENT_UUID` | Recommended | UUID of registered identity-agent |
| `ENDPOINT_AGENT_UUID` | Recommended | UUID of registered endpoint-agent |
| `HISTORICAL_CONTEXT_AGENT_UUID` | Recommended | UUID of registered historical-context-agent |

At least one sub-agent UUID should be set or the agent will process alerts with LLM only.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export CALSETA_API_URL=http://localhost:8000
export CALSETA_AGENT_KEY=cak_your_key_here
export ANTHROPIC_API_KEY=sk-ant-...
export THREAT_INTEL_AGENT_UUID=<uuid>
export IDENTITY_AGENT_UUID=<uuid>
export ENDPOINT_AGENT_UUID=<uuid>
export HISTORICAL_CONTEXT_AGENT_UUID=<uuid>

# Process next alert from queue
python agent.py --mode queue

# Handle a delegated invocation
python agent.py --mode invocation --invocation-id <uuid>
```

## Output

The agent posts a structured finding to the alert with:
- Full investigation verdict (True Positive / False Positive / Requires Further Investigation)
- Confidence assessment (High / Medium / Low)
- Summary of what happened based on evidence
- Key evidence from each specialist
- Ordered recommended actions
- Analyst notes for on-call review

If the LLM recommends containment, actions are also proposed via `POST /v1/actions` for human-in-the-loop approval.
