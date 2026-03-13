"""
Seed sandbox context documents — 3 docs with targeting rules matching fixture scenarios.

Idempotent: checks (title, is_system=True) before inserting.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.context_document import ContextDocument

logger = structlog.get_logger(__name__)


_SANDBOX_DOCS: list[dict[str, object]] = [
    {
        "title": "Identity Compromise Investigation Runbook",
        "document_type": "runbook",
        "description": "Step-by-step investigation guide for identity-based attacks",
        "content": (
            "# Identity Compromise Investigation Runbook\n\n"
            "## Scope\n"
            "This runbook covers brute force attacks, impossible travel alerts, "
            "credential stuffing, and suspicious sign-in activity.\n\n"
            "## Investigation Steps\n"
            "1. **Verify the alert** — confirm the source IP, target account, and "
            "timestamp are consistent.\n"
            "2. **Check account status** — query Okta/Entra for current account "
            "status, MFA enrollment, and recent password changes.\n"
            "3. **Review sign-in history** — look for successful authentications "
            "from the suspicious IP within 24 hours.\n"
            "4. **Assess lateral movement** — check if the compromised account "
            "accessed any new resources or elevated privileges.\n"
            "5. **IP reputation** — enrich the source IP via VirusTotal and "
            "AbuseIPDB. TOR exit nodes and known VPN providers are expected for "
            "some attack patterns.\n\n"
            "## Response Actions\n"
            "- **Confirmed compromise**: Suspend account, revoke sessions, "
            "reset password, notify user.\n"
            "- **Suspicious but unconfirmed**: Enable step-up MFA, monitor for "
            "24 hours, create conditional access policy blocking the IP range.\n"
            "- **False positive**: Document the legitimate travel/VPN usage and "
            "close as False Positive - Legitimate Activity.\n"
        ),
        "targeting_rules": {
            "match_any": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
                {"field": "tags", "op": "contains", "value": "IdentityThreat"},
            ]
        },
        "tags": ["identity", "brute-force", "impossible-travel"],
    },
    {
        "title": "Malware Detection and Containment SOP",
        "document_type": "sop",
        "description": "Standard operating procedure for malware hash detections",
        "content": (
            "# Malware Detection and Containment SOP\n\n"
            "## Scope\n"
            "Applies to alerts involving known malware hashes, suspicious "
            "executables, or encoded command execution.\n\n"
            "## Immediate Actions (within 15 minutes)\n"
            "1. **Isolate the host** — use the endpoint agent to network-isolate "
            "the affected machine.\n"
            "2. **Verify the hash** — check VirusTotal for detection ratio and "
            "malware family classification.\n"
            "3. **Identify the user** — determine which user account was active "
            "on the host at the time of detection.\n\n"
            "## Analysis\n"
            "4. **Decode encoded commands** — base64 decode any PowerShell "
            "-EncodedCommand payloads to identify C2 domains.\n"
            "5. **Check network connections** — look for outbound connections to "
            "the C2 domain/IP from any host in the environment.\n"
            "6. **Scope the incident** — search for the same hash across all "
            "endpoints in the last 7 days.\n\n"
            "## Containment\n"
            "7. **Block indicators** — add malicious domains and IPs to the "
            "firewall block list.\n"
            "8. **Quarantine the file** — ensure the endpoint agent has "
            "quarantined the file.\n"
            "9. **Collect forensic artifacts** — memory dump, event logs, "
            "prefetch files.\n"
        ),
        "targeting_rules": {
            "match_any": [
                {"field": "source_name", "op": "eq", "value": "elastic"},
                {"field": "severity", "op": "in", "value": ["Critical", "High"]},
            ]
        },
        "tags": ["malware", "containment", "powershell"],
    },
    {
        "title": "Data Exfiltration Investigation Plan",
        "document_type": "ir_plan",
        "description": "Investigation plan for anomalous data transfer alerts",
        "content": (
            "# Data Exfiltration Investigation Plan\n\n"
            "## Scope\n"
            "Covers anomalous data transfers, unusual upload volumes, and "
            "connections to suspicious external destinations.\n\n"
            "## Triage\n"
            "1. **Identify the user and service account** — determine if the "
            "transfer was initiated by a human or automated process.\n"
            "2. **Check destination reputation** — enrich the destination "
            "domain/IP. Known cloud storage providers (Dropbox, Google Drive) "
            "may be legitimate but still require verification.\n"
            "3. **Quantify the transfer** — how much data was transferred? "
            "Compare against the user's 30-day baseline.\n\n"
            "## Deep Dive\n"
            "4. **Review DLP alerts** — check if any Data Loss Prevention "
            "policies were triggered.\n"
            "5. **Inspect the payload** — if possible, identify file types "
            "and content categories in the transfer.\n"
            "6. **Timeline analysis** — was the transfer during business hours? "
            "Was the user's account accessed from an unusual location?\n\n"
            "## Response\n"
            "7. **Block the destination** — if confirmed malicious, add to "
            "proxy/firewall block list.\n"
            "8. **Preserve evidence** — retain network flow logs and proxy "
            "logs for the investigation window.\n"
        ),
        "targeting_rules": {
            "match_any": [
                {"field": "source_name", "op": "eq", "value": "splunk"},
                {"field": "tags", "op": "contains", "value": "Exfiltration"},
            ]
        },
        "tags": ["exfiltration", "data-transfer", "dlp"],
    },
]


async def seed_sandbox_context_documents(db: AsyncSession) -> list[ContextDocument]:
    """Seed sandbox context documents. Idempotent — skips existing docs."""
    created: list[ContextDocument] = []

    for spec in _SANDBOX_DOCS:
        existing = await db.execute(
            select(ContextDocument).where(
                ContextDocument.title == spec["title"],
                ContextDocument.is_system.is_(True),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        doc = ContextDocument(
            title=spec["title"],  # type: ignore[arg-type]
            document_type=spec["document_type"],  # type: ignore[arg-type]
            description=spec.get("description"),  # type: ignore[arg-type]
            content=spec["content"],  # type: ignore[arg-type]
            targeting_rules=spec.get("targeting_rules"),  # type: ignore[arg-type]
            tags=spec.get("tags", []),  # type: ignore[arg-type]
            is_global=False,
            is_system=True,
        )
        db.add(doc)
        created.append(doc)

    if created:
        await db.flush()
        logger.info("sandbox_context_documents_seeded", count=len(created))

    return created
