# Identity Agent

A specialist agent that assesses account compromise risk from identity indicators (UPN, email, account ID). Uses Calseta's Okta and Microsoft Entra enrichment results, and documents patterns for deeper Microsoft Graph API and Okta API calls.

## What It Does

1. Extracts account and email indicators from the alert (indicators list + raw_payload fallback)
2. Fetches Calseta enrichment for each account (Okta/Entra results from built-in providers)
3. Documents which Graph API and Okta API calls would provide additional context
4. Calls Claude to assess compromise risk with recommended actions (session revocation, MFA re-registration, account disable)
5. Posts an invocation result with risk level and prioritized recommended actions

## External Identity API Integration

The agent documents API stubs for:

**Microsoft Graph API** (`ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID`):
- User profile + account enabled status
- Sign-in logs with geolocation and device details
- MFA registration methods
- Group memberships (for blast radius)

**Okta API** (`OKTA_DOMAIN`, `OKTA_API_TOKEN`):
- User profile + account status
- Active sessions
- System log events

Look for `# TODO: implement API call` comments in `agent.py`.

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
    "name": "identity-agent",
    "execution_mode": "external",
    "agent_type": "specialist",
    "role": "identity",
    "adapter_type": "http",
    "endpoint_url": "http://your-agent-host:8103"
  }'
```
