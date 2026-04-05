# Reference Agents — Agent Navigation

## What Reference Agents Are (and Aren't)

The agents in `examples/agents/` are **working reference implementations** — production-quality patterns to fork, not toy examples or demos. They demonstrate correct usage of the Calseta API for real SOC investigation workflows.

They are **not** managed agents. Reference agents run as standalone Python scripts outside Calseta's control plane — they authenticate as external agents using `cak_*` keys, call the Calseta REST API directly, and are responsible for their own execution lifecycle. Calseta does not schedule or supervise them.

Use these as starting points when building a new agent that will integrate with Calseta.

## Directory Structure

```
examples/agents/
├── lead-investigator/      # Orchestrator: checks out alerts, delegates to specialists
├── threat-intel-agent/     # Specialist: enriches indicators via external TI sources
├── identity-agent/         # Specialist: investigates account/identity indicators
├── endpoint-agent/         # Specialist: analyzes host/process indicators
├── historical-context-agent/  # Specialist: searches prior similar alerts
├── response-agent/         # Specialist: executes containment actions
└── siem-query-agent/       # Specialist: queries SIEM for additional context
```

Each agent directory contains:
- `agent.py` — main executable; run with `python agent.py --mode queue` or `--mode invocation`
- `system_prompt.md` — LLM system prompt (loaded at runtime, not hardcoded)
- `README.md` — registration payload, env vars, quick start
- `capabilities.json` — tool/capability definitions
- `config.example.json` — configuration template
- `requirements.txt` — Python dependencies

## Two Invocation Modes

Every reference agent supports two modes via `--mode`:

### Queue mode (`--mode queue`)

The agent polls the alert queue, checks out an alert, investigates it, and posts a finding. This is the standalone execution model.

```bash
python lead-investigator/agent.py --mode queue
```

Internal flow:
1. `GET /v1/queue` — find eligible alerts
2. `POST /v1/queue/{alert_uuid}/checkout` — atomically claim one
3. Investigate (call specialists or do direct analysis)
4. `POST /v1/alerts/{alert_uuid}/findings` — post verdict
5. Optionally: `POST /v1/actions` — propose containment

### Invocation mode (`--mode invocation --invocation-id <uuid>`)

The agent handles a delegated task from an orchestrator. This is how specialists receive work.

```bash
python threat-intel-agent/agent.py --mode invocation --invocation-id "abc-123-..."
```

Internal flow:
1. `GET /v1/invocations/{uuid}` — fetch the invocation payload (task details, alert context)
2. Do the specialized analysis
3. `PATCH /v1/invocations/{uuid}` — post result (success/failure + findings)

## How to Register a Reference Agent in Calseta

Before an agent can checkout alerts or receive invocations, register it:

```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Authorization: Bearer cai_your_operator_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "lead-investigator",
    "description": "Orchestrator: coordinates specialist agents for alert triage",
    "agent_type": "orchestrator",          # "orchestrator" or "specialist"
    "execution_mode": "external",          # "external" for scripts like these
    "adapter_type": "webhook",
    "endpoint_url": "https://your-host/webhook",  # optional for external agents
    "role": "lead_investigator",
    "trigger_on_sources": [],              # empty = all sources
    "trigger_on_severities": ["High", "Critical"],
    "timeout_seconds": 300,
    "retry_count": 3
  }'
```

Then create an agent API key:

```bash
curl -X POST http://localhost:8000/v1/agents/{agent_uuid}/keys \
  -H "Authorization: Bearer cai_your_operator_key" \
  -H "Content-Type: application/json" \
  -d '{"name": "prod-key-1"}'
```

The response includes the `cak_*` key shown once — save it as `CALSETA_AGENT_KEY` in the agent's environment.

## Auth Pattern

Reference agents authenticate with agent API keys (`cak_*`), not operator keys (`cai_*`).

```python
HEADERS = {
    "Authorization": f"Bearer {os.environ['CALSETA_AGENT_KEY']}",
    "Content-Type": "application/json",
}
```

Agent keys differ from operator keys:
- `cak_*` keys identify the calling `AgentRegistration` row — `auth.agent_registration_id` is set
- Queue/checkout/invocation endpoints require `cak_*` — they return 403 with operator keys
- Operator keys (`cai_*`) are for human operators, not running agents

## How Specialists Receive Delegated Work

When the lead-investigator calls `POST /v1/invocations`, it creates an invocation record. The specialist is responsible for polling or being notified (implementation-specific). The invocation payload shape:

```json
GET /v1/invocations/{uuid}
{
  "data": {
    "uuid": "abc-123",
    "status": "pending",
    "task_type": "investigate_indicators",
    "payload": {
      "alert_uuid": "...",
      "indicator_types": ["ip", "domain"],
      "context": "Investigate these indicators for threat intelligence"
    },
    "orchestrator_agent_uuid": "...",
    "created_at": "2026-04-04T10:00:00Z"
  }
}
```

Fields to read:
- `payload.alert_uuid` — fetch alert details from `GET /v1/alerts/{uuid}`
- `payload.indicator_types` — which indicator types this specialist should focus on
- `payload.context` — free-form context from the orchestrator
- `orchestrator_agent_uuid` — the delegating agent (for logging)

## How to Post Results Back

After completing analysis, the specialist PATCHes the invocation:

```python
result_payload = {
    "status": "complete",          # or "failed"
    "result": {
        "verdict": "Malicious",
        "confidence": "High",
        "summary": "IP 1.2.3.4 is associated with Cobalt Strike C2 infrastructure.",
        "indicators_assessed": 3,
        "key_evidence": ["VT detections: 45/72", "AbuseIPDB confidence: 100%"],
    },
    "error": None,
}

response = requests.patch(
    f"{CALSETA_URL}/v1/invocations/{invocation_uuid}",
    headers=HEADERS,
    json=result_payload,
)
```

The `result` dict is free-form — the orchestrator decides how to interpret it. The `status` field must be `"complete"` or `"failed"`. On `"failed"`, set `error` to a human-readable explanation.

## How to Add a New Specialist

1. **Create the directory:**
   ```
   examples/agents/my-specialist/
   ├── agent.py
   ├── system_prompt.md
   ├── README.md
   ├── requirements.txt
   ├── capabilities.json
   └── config.example.json
   ```

2. **Copy the agent.py structure from an existing specialist** (e.g., `threat-intel-agent/agent.py`). Keep the two-mode entrypoint identical:
   ```python
   if args.mode == "queue":
       asyncio.run(run_queue_mode())
   elif args.mode == "invocation":
       asyncio.run(run_invocation_mode(args.invocation_id))
   ```

3. **Register the new specialist with the lead-investigator** — update `lead-investigator/agent.py:select_specialists()` to include the new agent's UUID and the alert conditions under which to invoke it.

4. **Document the registration payload** in `README.md` with the exact `POST /v1/agents` body (including `agent_type: "specialist"` and the correct `role`).

5. **Required env vars:** At minimum `CALSETA_URL` and `CALSETA_AGENT_KEY`. List all others in `README.md` and `config.example.json`.

## How to Extend an Existing Agent

**What to change:**
- `system_prompt.md` — update the role definition, output format, or evidence-weighting instructions
- `agent.py` analysis functions — add new API calls, change synthesis logic, add new indicator types to handle
- `capabilities.json` — add new capabilities if the agent should handle new task types

**What to keep identical:**
- The auth pattern (`CALSETA_AGENT_KEY`, `Authorization: Bearer` header)
- The two-mode entrypoint (`--mode queue` / `--mode invocation`)
- The result posting pattern (`PATCH /v1/invocations/{uuid}`)
- The finding posting pattern (`POST /v1/alerts/{uuid}/findings`)

Never change the auth pattern or result format — the orchestrator and Calseta platform depend on these being stable.

## The `# TODO: stub` Convention for External API Calls

Reference agents intentionally do NOT implement live calls to external APIs (VirusTotal, AbuseIPDB, Okta, etc.) — those require API keys the reader may not have. Instead, they document the call with a stub comment:

```python
# TODO: implement VirusTotal IP lookup
# Endpoint: GET https://www.virustotal.com/api/v3/ip_addresses/{ip}
# Auth: X-Apikey header with VIRUSTOTAL_API_KEY env var
# Response: data.attributes.last_analysis_stats.malicious (int)
# Rate limit: 4 requests/minute (free tier)
```

A valid stub comment must include:
- The endpoint URL (exact, not paraphrased)
- The auth method and env var name
- The response field(s) that contain the result
- The rate limit (if known)

This lets a reader implement the call without looking up docs. If you add an external API call to a reference agent, follow this convention — do not silently omit the API call or return a hardcoded value.

## Lead Investigator — Specialist Selection Logic

The lead investigator selects specialists based on the alert's indicators:

```python
def select_specialists(alert: dict) -> list[str]:
    """Rule-based specialist selection. Returns list of specialist agent UUIDs."""
    specialists = []
    indicator_types = {ind["type"] for ind in alert.get("indicators", [])}

    if indicator_types & {"ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url"}:
        specialists.append(THREAT_INTEL_AGENT_UUID)

    if indicator_types & {"account", "email"}:
        specialists.append(IDENTITY_AGENT_UUID)

    if indicator_types & {"hash_sha256", "hash_md5"}:  # process/file indicators
        specialists.append(ENDPOINT_AGENT_UUID)

    specialists.append(HISTORICAL_CONTEXT_AGENT_UUID)  # always included

    return specialists
```

Agent UUIDs are read from environment variables (`THREAT_INTEL_AGENT_UUID`, etc.) to avoid hardcoding. The orchestrator calls `POST /v1/invocations/parallel` with all selected specialists at once, then polls each invocation until complete.
