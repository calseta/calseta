# Response Agent

A specialist agent that translates investigation findings into a prioritized response action plan. Actions meeting the confidence threshold (default: 0.85) are automatically submitted to the Calseta approval gate for human-in-the-loop authorization.

## What It Does

1. Loads invocation context (includes synthesized findings from the lead-investigator orchestrator)
2. Fetches the alert and any existing investigation findings
3. Calls Claude with the IR specialist system prompt → generates prioritized action list with confidence scores
4. For each action with `confidence >= 0.85`: `POST /v1/actions` (enters approval gate)
5. Posts invocation result with full action list and submission count

## Confidence Threshold

The threshold is configurable via the `ACTION_CONFIDENCE_THRESHOLD` environment variable (default: `0.85`).

Actions below the threshold are included in the recommendation list (in the invocation result) but are not auto-submitted — they require an analyst to manually submit or dismiss them.

## Action Types

| Type | Phase | Reversible |
|---|---|---|
| `block_ip` | Contain | Yes |
| `block_domain` | Contain | Yes |
| `revoke_session` | Contain | Yes |
| `disable_account` | Contain | Partially |
| `isolate_host` | Contain | Partially |
| `quarantine_file` | Contain | Yes |
| `force_mfa_reregister` | Remediate | Partially |
| `force_password_reset` | Remediate | Partially |
| `remove_persistence` | Remediate | Partially |
| `notify_user_manager` | Escalate | Yes |
| `escalate_to_tier2` | Escalate | Yes |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CALSETA_API_URL` | No | Calseta API base URL (default: `http://localhost:8000`) |
| `CALSETA_AGENT_KEY` | Yes | Agent API key (`cak_` prefix) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ACTION_CONFIDENCE_THRESHOLD` | No | Auto-submit threshold (default: `0.85`) |

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
    "name": "response-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "response",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8106",
    "trigger_on_severities": ["High", "Critical"]
  }'
```
