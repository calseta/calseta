"""
Seed sandbox detection rules — 5 rules matching the case study fixture scenarios.

Idempotent: checks (name, is_system=True) before inserting.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.detection_rule import DetectionRule

logger = structlog.get_logger(__name__)


@dataclass
class _RuleSpec:
    name: str
    source_name: str
    source_rule_id: str
    severity: str
    mitre_tactics: list[str]
    mitre_techniques: list[str]
    documentation: str


_SANDBOX_RULES: list[_RuleSpec] = [
    _RuleSpec(
        name="Brute Force Sign-In Attempts from TOR Network",
        source_name="sentinel",
        source_rule_id="d1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a",
        severity="High",
        mitre_tactics=["InitialAccess", "CredentialAccess"],
        mitre_techniques=["T1110", "T1110.001"],
        documentation=(
            "Detects multiple failed sign-in attempts originating from known TOR exit "
            "nodes. Threshold: 5+ failures within 10 minutes from a TOR IP. Investigate "
            "the target account for compromise, check if the TOR IP has succeeded on any "
            "other account, and consider blocking at the conditional access policy level."
        ),
    ),
    _RuleSpec(
        name="Known Malware Hash Detected on Endpoint",
        source_name="elastic",
        source_rule_id="a9b0c1d2-e3f4-5678-9abc-def012345678",
        severity="Critical",
        mitre_tactics=["Execution"],
        mitre_techniques=["T1204", "T1204.002"],
        documentation=(
            "Triggers when a file with a hash matching known malware signatures is "
            "detected on an endpoint. Immediately isolate the host, collect a memory "
            "dump, and check lateral movement indicators. Verify the hash against "
            "VirusTotal for family classification and extract C2 domains from sandbox "
            "reports."
        ),
    ),
    _RuleSpec(
        name="Anomalous Large Data Transfer to External Destination",
        source_name="splunk",
        source_rule_id="splunk-notable-anomalous-transfer",
        severity="High",
        mitre_tactics=["Exfiltration"],
        mitre_techniques=["T1048", "T1048.001"],
        documentation=(
            "Detects data transfers exceeding baseline thresholds to external "
            "destinations. Check the destination domain/IP reputation, verify the "
            "user account is expected to transfer large volumes, and inspect the "
            "transfer protocol. Correlate with DLP alerts and check if the destination "
            "is a known cloud storage or file sharing service."
        ),
    ),
    _RuleSpec(
        name="Impossible Travel Activity Detected",
        source_name="sentinel",
        source_rule_id="e7f8a9b0-c1d2-4e3f-a5b6-c7d8e9f01234",
        severity="High",
        mitre_tactics=["InitialAccess"],
        mitre_techniques=["T1078", "T1078.004"],
        documentation=(
            "Detects authentication events from geographically distant locations within "
            "an impossibly short timeframe. Check if the user has VPN or proxy access that "
            "could explain the travel, verify device fingerprints, and review the anomalous "
            "IP for previous associations with the user. High-privilege accounts (Global "
            "Admin) require immediate investigation."
        ),
    ),
    _RuleSpec(
        name="Suspicious PowerShell Execution with Encoded Command",
        source_name="elastic",
        source_rule_id="a9b0c1d2-e3f4-5678-9abc-def012345678",
        severity="High",
        mitre_tactics=["Execution", "DefenseEvasion"],
        mitre_techniques=["T1059.001", "T1027"],
        documentation=(
            "Detects PowerShell execution with encoded commands, especially combined "
            "with execution policy bypass and hidden windows. Decode the base64 command "
            "to identify the payload, check destination domains/IPs for C2 indicators, "
            "and inspect the parent process chain for lateral movement or initial access "
            "vectors."
        ),
    ),
]


async def seed_sandbox_detection_rules(db: AsyncSession) -> list[DetectionRule]:
    """Seed sandbox detection rules. Idempotent — skips existing rules."""
    created: list[DetectionRule] = []

    for spec in _SANDBOX_RULES:
        existing = await db.execute(
            select(DetectionRule).where(
                DetectionRule.name == spec.name,
                DetectionRule.is_system.is_(True),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        rule = DetectionRule(
            name=spec.name,
            source_name=spec.source_name,
            source_rule_id=spec.source_rule_id,
            severity=spec.severity,
            is_active=True,
            is_system=True,
            mitre_tactics=spec.mitre_tactics,
            mitre_techniques=spec.mitre_techniques,
            documentation=spec.documentation,
        )
        db.add(rule)
        created.append(rule)

    if created:
        await db.flush()
        logger.info("sandbox_detection_rules_seeded", count=len(created))

    return created
