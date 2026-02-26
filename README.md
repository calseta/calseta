# Calseta

**The open-source data layer for security AI agents.**

Calseta ingests security alerts from any SIEM, normalizes them to a common schema, enriches them with threat intelligence and identity context, and delivers clean, structured payloads to your AI agents — so agents spend their tokens on reasoning, not plumbing.

> **Status: Active development.** Calseta is currently being built toward an initial MVP release. The architecture and API design are stable. Core functionality is not yet complete. Watch or star this repo to follow along.

---

## The Problem

Security teams building AI agents for alert investigation consistently hit the same walls:

- **Context gap** — agents lack access to detection rule documentation, runbooks, IR plans, and SOPs. Without organizational context, agents produce generic output.
- **Integration burden** — investigating a single alert requires calling 5+ external APIs. Each integration is custom code that's expensive to build and fragile to maintain.
- **Token waste** — raw API responses are verbose and unstructured. Agents stuffing them into context windows burn tokens and produce worse output.
- **No deterministic layer** — enrichment, normalization, and alert routing are deterministic tasks that should never consume LLM tokens. Today, agents do this themselves because no purpose-built infrastructure exists.

Calseta handles all of it before your agent sees a single byte.

---

## How It Works

Every alert passes through five deterministic steps:

```
Alert Source → Ingest → Normalize (OCSF) → Enrich → Contextualize → Dispatch
                                                                          │
                                                         Your AI Agent ←──┘
                                                         (webhook or MCP)
```

1. **Ingest** — alerts arrive via webhook from Sentinel, Elastic, Splunk, or any OCSF-compatible source
2. **Normalize** — mapped to OCSF Security Finding schema (class_uid: 2001), source preserved
3. **Enrich** — indicators (IPs, domains, hashes, accounts) enriched in parallel via VirusTotal, AbuseIPDB, Okta, and Entra
4. **Contextualize** — detection rule docs, runbooks, IR plans, SOPs, and workflow documentation attached via targeting rules
5. **Dispatch** — enriched payload delivered to registered agents via webhook, or pulled via REST API or MCP

Your agent receives one structured object with everything it needs to investigate and respond.

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

# → {"key": "csk_...", "show_once": true}
```

Full setup guide and configuration reference at [docs.calseta.com](https://docs.calseta.com).

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
    "source": "sentinel"
  },
  "indicators": [
    {
      "type": "ip",
      "value": "185.220.101.47",
      "virustotal": { "malicious": 14, "suspicious": 2 },
      "abuseipdb": { "score": 97, "categories": ["hacking"] }
    }
  ],
  "detection_rule": {
    "name": "Suspicious Auth v2",
    "mitre_tactics": ["TA0001", "TA0006"],
    "documentation": "## Overview\nDetects impossible travel..."
  },
  "context_documents": [
    { "title": "Identity IR Runbook", "type": "runbook", "content": "..." }
  ],
  "workflows": [
    { "name": "Account Compromise Response", "documentation": "..." }
  ]
}
```

---

## Features

| Feature | Description |
|---|---|
| **Alert ingestion** | Plugin-based. Ships with Sentinel, Elastic, Splunk, and generic OCSF webhook |
| **OCSF normalization** | Every alert normalized to Security Finding (class_uid: 2001) |
| **Enrichment engine** | Async, parallel, cached. VirusTotal, AbuseIPDB, Okta, Entra |
| **Detection rule library** | Auto-created on ingestion. MITRE-mapped with markdown documentation |
| **Context documents** | Runbooks, IR plans, SOPs — attached to alerts via targeting rules |
| **Workflow catalog** | SOC playbooks as structured markdown, surfaced to agents as context |
| **REST API** | Full CRUD across all entities. OpenAPI spec included |
| **MCP server** | Native MCP on port 8001. Works with any MCP-compatible agent or tool |
| **Metrics API** | Alert volume, MTTD, false positive rates — accessible via REST and MCP |
| **API key auth** | Scoped API keys for agent access |

---

## Adding an Alert Source

Implement one class:

```python
from app.integrations.sources.base import AlertSourceBase

class MySource(AlertSourceBase):
    def validate_payload(self, raw: dict) -> bool: ...
    def normalize(self, raw: dict) -> OCSFSecurityFinding: ...
    def extract_indicators(self, normalized: OCSFSecurityFinding) -> list[Indicator]: ...
```

Register it and alerts from that source flow through the full pipeline automatically. See `docs/adding-alert-sources.md`.

---

## Adding an Enrichment Provider

```python
from app.integrations.enrichment.base import EnrichmentProviderBase

class MyProvider(EnrichmentProviderBase):
    supported_types = [IndicatorType.IP, IndicatorType.DOMAIN]

    async def enrich(self, indicator: Indicator) -> EnrichmentResult: ...
```

See `docs/adding-enrichment-providers.md`.

---

## Examples

The `/examples` directory contains runnable reference implementations:

| Example | Description |
|---|---|
| `simple-triage-agent/` | Start here. Raw SDK agent (~60 lines) that receives and responds to a Calseta webhook |
| `slack-bot/` | Slack as a dispatch consumer — posts alert findings to a channel |
| `workflow-examples/` | Deterministic Python scripts for auto-tagging and false positive handling |
| `langgraph-investigation/` | Multi-step LangGraph agent for complex incident investigation |

---

## Tech Stack

Python 3.12 · FastAPI · PostgreSQL 15 · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · procrastinate · httpx · MCP Python SDK · Docker

---

## Project Status

Calseta is actively being built. Current progress:

- [x] Architecture and API design finalized
- [x] Project scaffold and Docker Compose
- [ ] Database schema and migrations
- [ ] Alert ingestion (Sentinel, Elastic, Splunk)
- [ ] OCSF normalization
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

- Additional alert source integrations
- Additional enrichment providers
- Bug reports and feedback on the API design

See `CONTRIBUTING.md` for how to get started. Please read `PLATFORM_DESIGN.md` before opening a PR — it explains the design decisions behind the architecture.

---

## Links

- **Docs:** [docs.calseta.com](https://docs.calseta.com)
- **Website:** [calseta.com](https://calseta.com)
- **License:** Apache 2.0

---

*Calseta is not an AI SOC product. It does not build, host, or run AI agents. It is the data infrastructure that makes your agents fast, accurate, and cost-efficient.*