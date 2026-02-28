# Calseta

**The open-source data layer for security agents.**

Calseta ingests security alerts from any SIEM, enriches them with threat intelligence and identity context, and delivers clean, structured payloads to your security agents — so agents spend their tokens on reasoning, not plumbing.

> **Status: Active development.** Calseta is currently being built toward an initial MVP release. The architecture and API design are stable. Core functionality is not yet complete. Watch or star this repo to follow along.

---

## The Problem

Security teams building AI agents for alert investigation consistently hit the same walls:

- **Context gap** — agents lack access to detection rule documentation, runbooks, IR plans, and SOPs. Without organizational context, agents produce generic output.
- **Integration burden** — investigating a single alert requires calling 5+ external APIs. Each integration is custom code that's expensive to build and fragile to maintain.
- **Token waste** — raw API responses are verbose and unstructured. Agents stuffing them into context windows burn tokens and produce worse output.
- **No deterministic layer** — enrichment and alert routing are deterministic tasks that should never consume LLM tokens. Today, agents do this themselves because no purpose-built infrastructure exists.

Calseta handles all of it before your agent sees a single byte.

---

## How It Works

Every alert passes through five deterministic steps:

```
Alert Source → Ingest → Normalize → Enrich → Contextualize → Dispatch
                                                                   │
                                                    Your AI Agent ←──┘
                                                    (webhook or MCP)
```

1. **Ingest** — alerts arrive via webhook from Sentinel, Elastic, Splunk, or any compatible source
2. **Normalize** — mapped to a clean, agent-readable schema; source-specific fields preserved in `raw_payload`
3. **Enrich** — indicators (IPs, domains, hashes, accounts) enriched in parallel via VirusTotal, AbuseIPDB, Okta, and Entra
4. **Contextualize** — detection rule docs, runbooks, IR plans, SOPs, and workflow documentation attached via targeting rules
5. **Dispatch** — enriched payload delivered to registered agents via webhook, or pulled via REST API or MCP

Your agent receives one structured object with everything it needs to investigate and respond.

---

## Why Not OCSF?

OCSF is designed for data producers — EDR vendors, network appliances, identity providers — to map their fields to a common schema so security teams can ingest from diverse sources into a SIEM. The design choices reflect that goal: numeric class IDs, epoch timestamps, and `unmapped` buckets optimized for machine indexing and SIEM storage.

That's the wrong tradeoff for AI agents.

Calseta normalizes to its own agent-native schema: human-readable field names, enrichment data as first-class output rather than an afterthought, and organizational context baked into every payload. Indicators also live in a relational table keyed by `(type, value)` — a global entity model that tracks IOC history across alerts in a way that doesn't fit OCSF's flat structure.

The goal is agents that spend tokens on reasoning, not parsing.

---

## Quickstart

```bash
git clone https://github.com/calseta/calseta
cd calseta
cp .env.example .env
docker compose up
```

Three services start: API server (`localhost:8000`), MCP server (`localhost:8001`), PostgreSQL (`localhost:5432`).

```bash
# Create an API key
curl -X POST localhost:8000/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent"}'

# → {"key": "cai_...", "show_once": true}
```

Full setup guide at `docs/DEVELOPMENT.md`. Production deployment at `docs/HOW_TO_DEPLOY.md`.

---

## What Your Agent Receives

A single enriched payload on every alert:

```json
{
  "event": "alert.enriched",

  "alert": {
    "uuid": "9f2a-b3c1-...",
    "title": "Impossible Travel Detected",
    "severity": "High",
    "source": "elastic",
    "status": "Open",
    "created_at": "2025-01-15T03:42:18.441Z"
  },

  "indicators": [
    {
      "type": "ip",
      "value": "185.220.101.47",
      "first_seen": "2024-08-12T00:00:00.000Z",
      "last_seen": "2025-01-15T03:42:18.441Z",
      "geo": { "country": "Germany", "city": "Frankfurt am Main" },
      "virustotal": { "malicious": 14, "suspicious": 2, "score": "47/94" },
      "abuseipdb": { "score": 97, "categories": ["hacking", "vpn"] },
      "greynoise": { "classification": "malicious", "name": "TOR Exit Node", "noise": true }
    },
    {
      "type": "ip",
      "value": "67.180.201.3",
      "first_seen": "2022-03-05T00:00:00.000Z",
      "last_seen": "2025-01-15T01:10:42.000Z",
      "geo": { "country": "United States", "city": "San Francisco" },
      "virustotal": { "malicious": 0, "suspicious": 0, "score": "0/94" },
      "abuseipdb": { "score": 4, "categories": [] }
    },
    {
      "type": "account",
      "value": "nick.hathaway@calseta.com",
      "okta": {
        "status": "ACTIVE",
        "profile": {
          "full_name": "Nick Hathaway",
          "title": "Senior Software Engineer",
          "department": "Engineering",
          "employee_type": "employee",
          "location": "San Francisco, CA, US",
          "manager": "Emily Rhodes",
          "manager_email": "emily.rhodes@calseta.com"
        },
        "account_created": "2022-03-14T09:00:00.000Z",
        "last_login": "2025-01-14T22:31:05.000Z",
        "last_password_change": "2024-10-01T11:23:44.000Z",
        "mfa_factors": [
          { "type": "push", "provider": "OKTA", "status": "ACTIVE" },
          { "type": "totp", "provider": "GOOGLE", "status": "ACTIVE" }
        ],
        "group_membership": ["Engineering", "VPN-Users", "github-org-members"]
      }
    }
  ],

  "detection_rule": {
    "name": "Impossible Travel",
    "rule_id": "impossible-travel-v1",
    "severity": "High",
    "priority": "High — likely credential compromise or session hijacking",
    "mitre_tactics": ["TA0001 - Initial Access", "TA0005 - Defense Evasion", "TA0006 - Credential Access"],
    "mitre_techniques": ["T1078 - Valid Accounts"],
    "false_positive_tags": ["vpn", "corporate_proxy", "executive_travel"],
    "blind_spots": ["same-region cross-state travel", "VPN or proxy exit nodes"],
    "goal": "Detect credential compromise or session hijacking via geo-velocity analysis.",
    "documentation": "## Overview\nCorrelates sign-in timestamps and geolocation to flag logins from two countries within a short window — physically impossible without credential theft or session hijacking.\n\n## Responses\n1. Confirm travel or VPN activity with user\n2. Force sign-out and reset credentials\n3. Review concurrent risky sign-in alerts\n4. Notify SOC team of potential compromise"
  },

  "past_alerts": [
    {
      "uuid": "3c1d-a2f4-...",
      "title": "Impossible Travel Detected",
      "status": "closed",
      "classification": "true_positive_suspicious_activity",
      "closed_at": "2024-11-03T14:22:00.000Z",
      "indicators": ["91.108.56.130", "nick.hathaway@calseta.com"],
      "analyst_notes": "Confirmed malicious. Sessions revoked. Password reset. INC-2847."
    }
  ],

  "context_documents": [
    {
      "title": "Company Incident Response Plan",
      "type": "ir_plan",
      "content": "## Incident Response Plan\n1. Detect & triage\n2. Contain affected accounts\n3. Notify security lead\n4. Preserve evidence\n5. Remediate & recover..."
    },
    {
      "title": "Account Compromise Runbook",
      "type": "runbook",
      "content": "## Account Compromise Response\n1. Isolate account\n2. Revoke active sessions\n3. Force password reset\n4. Re-enroll MFA..."
    }
  ],

  "workflows": [
    { "name": "Revoke User Sessions", "description": "Terminate all active sessions for the affected account across all providers." },
    { "name": "Force Password Reset", "description": "Expire current credentials and require the user to set a new password on next login." },
    { "name": "Request User Attestation", "description": "Send the user a confirmation request to verify whether the activity was theirs." },
    { "name": "Notify Security Team", "description": "Page the on-call analyst and open a P1 incident ticket for human review." }
  ]
}
```

---

## Features

| Feature | Description |
|---|---|
| **Alert ingestion** | Plugin-based. Ships with Sentinel, Elastic, Splunk, and generic webhook |
| **Enrichment engine** | Async, parallel, cached. VirusTotal, AbuseIPDB, Okta, Entra |
| **Detection rule library** | Auto-created on ingestion. MITRE-mapped with markdown documentation |
| **Context documents** | Runbooks, IR plans, SOPs — attached to alerts via targeting rules |
| **Workflow catalog** | SOC playbooks as structured markdown, surfaced to agents as context |
| **REST API** | Full CRUD across all entities. OpenAPI spec included |
| **MCP server** | Native MCP on port 8001. Works with any MCP-compatible agent or tool |
| **Metrics API** | Alert volume, MTTD, false positive rates — accessible via REST and MCP |
| **API key auth** | Scoped API keys for agent access |

---

## Tech Stack

Python 3.12 · FastAPI · PostgreSQL 15 · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · procrastinate · httpx · MCP Python SDK · Docker

---

## Project Status

Calseta is actively being built. Current progress:

- [ ] Architecture and API design finalized
- [ ] Project scaffold and Docker Compose
- [ ] Database schema and migrations
- [ ] Alert ingestion (Sentinel, Elastic, Splunk)
- [ ] Enrichment engine (VirusTotal, AbuseIPDB, Okta, Entra)
- [ ] Context document system
- [ ] Agent registry and webhook dispatch
- [ ] REST API (full)
- [ ] MCP server
- [ ] Examples

This checklist will be updated as chunks complete. Track detailed progress in `PROJECT_PLAN.md`.

---

## Contributing

Contributions are welcome. The most valuable areas right now:

- Bug reports and feedback on the API design
- Review of the architecture and data model
- Additional alert source and enrichment provider integrations (once the core is built)

See `CONTRIBUTING.md` for how to get started. Read `CLAUDE.md` and `PRD.md` before opening a PR — they cover architecture decisions, coding philosophy, and extension patterns.

The platform is designed for extension. Both the alert source and enrichment provider systems use clean plugin interfaces — adding a new source or provider is one file with no core changes required. Full how-to guides (`docs/HOW_TO_ADD_ALERT_SOURCE.md`, `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`) and runnable example agents ship with the v1 release.

---

## Links

- **Website:** [calseta.com](https://calseta.com)
- **License:** Apache 2.0

---

*Calseta is not an AI SOC product. It does not build, host, or run AI agents. It is the data infrastructure that makes your agents fast, accurate, and cost-efficient.*
