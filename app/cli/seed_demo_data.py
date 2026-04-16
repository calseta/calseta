"""
Seed the database with realistic demo data for testing and demos.

Creates detection rules, context documents, and ingests sample alerts
from each source type (Sentinel, Elastic, Splunk) with realistic
security scenarios.

Usage:
    python -m app.cli.seed_demo_data
    python -m app.cli.seed_demo_data --skip-alerts
    python -m app.cli.seed_demo_data --skip-enrichment

Docker:
    docker compose exec api python -m app.cli.seed_demo_data
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource
from app.logging_config import configure_logging
from app.queue.base import QueueMetrics, TaskQueueBase, TaskStatus
from app.repositories.detection_rule_repository import DetectionRuleRepository
from app.schemas.detection_rules import DetectionRuleCreate
from app.services.alert_ingestion import AlertIngestionService

configure_logging("cli")
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# No-op queue backend for --skip-enrichment
# ---------------------------------------------------------------------------


class _NoOpQueue(TaskQueueBase):
    """Silently discards all enqueued tasks."""

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, object],
        *,
        queue: str,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> str:
        return "noop-skipped"

    async def get_task_status(self, task_id: str) -> TaskStatus:
        return TaskStatus.SUCCESS

    async def get_queue_metrics(self) -> QueueMetrics:
        return QueueMetrics()

    async def start_worker(self, queues: list[str]) -> None:
        pass


# ---------------------------------------------------------------------------
# Detection rules
# ---------------------------------------------------------------------------

DETECTION_RULES: list[dict] = [
    {
        "name": "Suspicious PowerShell Execution",
        "source_name": "sentinel",
        "source_rule_id": "rule-uuid-abc123",
        "severity": "High",
        "mitre_tactics": ["Execution", "Defense Evasion"],
        "mitre_techniques": ["T1059"],
        "mitre_subtechniques": ["T1059.001"],
        "data_sources": ["Process creation", "Script block logging"],
        "run_frequency": "5m",
        "created_by": "SOC Engineering",
        "documentation": (
            "# Suspicious PowerShell Execution\n\n"
            "Detects PowerShell processes launched with encoded or obfuscated arguments, "
            "which is a common technique for executing malicious payloads while evading "
            "static detection.\n\n"
            "## Triage steps\n"
            "1. Check the decoded command content for known malicious patterns\n"
            "2. Verify whether the parent process is expected (e.g. explorer.exe vs cmd.exe)\n"
            "3. Look for network connections made by the PowerShell process\n"
            "4. Check if the user account is expected to run PowerShell on this host\n\n"
            "## False positive scenarios\n"
            "- SCCM/Intune management scripts using -EncodedCommand\n"
            "- Legitimate admin tooling (e.g. DSC configurations)\n"
        ),
    },
    {
        "name": "Brute Force Login Attempt",
        "source_name": "splunk",
        "source_rule_id": "Brute Force Login Attempt",
        "severity": "High",
        "mitre_tactics": ["Credential Access", "Initial Access"],
        "mitre_techniques": ["T1110"],
        "mitre_subtechniques": ["T1110.001"],
        "data_sources": ["Authentication logs", "Windows Event Log"],
        "run_frequency": "5m",
        "created_by": "SOC Engineering",
        "documentation": (
            "# Brute Force Login Attempt\n\n"
            "Triggers when more than 10 failed login attempts from a single source IP "
            "are observed within a 5-minute window.\n\n"
            "## Triage steps\n"
            "1. Confirm the source IP and determine if it's internal or external\n"
            "2. Check if the targeted account is a service account or privileged user\n"
            "3. Verify whether any login succeeded after the failed attempts\n"
            "4. Look for the source IP across other log sources for lateral movement\n\n"
            "## False positive scenarios\n"
            "- Misconfigured service accounts with expired credentials\n"
            "- Users who forgot their password after a vacation\n"
        ),
    },
    {
        "name": "Malware Hash Match — Endpoint",
        "source_name": "elastic",
        "source_rule_id": "rule-uuid-elastic-malware",
        "severity": "Critical",
        "mitre_tactics": ["Execution"],
        "mitre_techniques": ["T1204"],
        "mitre_subtechniques": ["T1204.002"],
        "data_sources": ["File monitoring", "Process creation"],
        "run_frequency": "1m",
        "created_by": "Threat Intel Team",
        "documentation": (
            "# Malware Hash Match — Endpoint\n\n"
            "Fires when a file hash observed on an endpoint matches a known-malicious "
            "hash from the threat intelligence feed.\n\n"
            "## Triage steps\n"
            "1. Confirm the file is still present on the endpoint\n"
            "2. Check VirusTotal for community verdicts and sandbox reports\n"
            "3. Determine the delivery vector (email attachment, USB, web download)\n"
            "4. Isolate the host if the file was executed\n"
            "5. Check for persistence mechanisms (scheduled tasks, registry run keys)\n\n"
            "## False positive scenarios\n"
            "- Penetration testing tools flagged by hash\n"
            "- Old malware samples in quarantine directories\n"
        ),
    },
    {
        "name": "Impossible Travel — User Sign-In",
        "source_name": "sentinel",
        "source_rule_id": "rule-uuid-impossible-travel",
        "severity": "Medium",
        "mitre_tactics": ["Initial Access"],
        "mitre_techniques": ["T1078"],
        "mitre_subtechniques": ["T1078.004"],
        "data_sources": ["Azure AD sign-in logs", "Conditional Access"],
        "run_frequency": "15m",
        "created_by": "Identity Security Team",
        "documentation": (
            "# Impossible Travel — User Sign-In\n\n"
            "Detects when a user authenticates from two geographically distant locations "
            "within a time window that makes physical travel impossible.\n\n"
            "## Triage steps\n"
            "1. Check if one of the locations is a known VPN egress point\n"
            "2. Verify with the user whether they are traveling or using a VPN\n"
            "3. Check the user agent strings — different devices suggest compromise\n"
            "4. Look for suspicious mailbox rules or file access after the sign-in\n\n"
            "## False positive scenarios\n"
            "- Users connecting through corporate VPN (IP geolocates to HQ)\n"
            "- Mobile device switching between Wi-Fi and cellular\n"
        ),
    },
    {
        "name": "Data Exfiltration via DNS Tunneling",
        "source_name": "splunk",
        "source_rule_id": "DNS Tunneling Exfiltration",
        "severity": "Critical",
        "mitre_tactics": ["Exfiltration", "Command and Control"],
        "mitre_techniques": ["T1048", "T1071"],
        "mitre_subtechniques": ["T1048.003", "T1071.004"],
        "data_sources": ["DNS logs", "Network flow"],
        "run_frequency": "5m",
        "created_by": "SOC Engineering",
        "documentation": (
            "# Data Exfiltration via DNS Tunneling\n\n"
            "Detects anomalous DNS query patterns consistent with DNS tunneling — "
            "high query volume, long subdomain labels, or high entropy domain names.\n\n"
            "## Triage steps\n"
            "1. Examine the queried domain names for base64 or hex encoding in subdomains\n"
            "2. Check the source host for running processes with network activity\n"
            "3. Correlate with proxy logs for the same timeframe\n"
            "4. Block the domain at the DNS resolver and monitor for fallback C2\n\n"
            "## False positive scenarios\n"
            "- CDN domains with long hostnames (e.g. akamai, cloudfront)\n"
            "- DKIM/SPF TXT record lookups\n"
        ),
    },
]


# ---------------------------------------------------------------------------
# Sample alert payloads
# ---------------------------------------------------------------------------


def _now_minus(hours: int = 0, minutes: int = 0) -> str:
    """Return an ISO 8601 timestamp offset from now."""
    dt = datetime.now(UTC) - timedelta(hours=hours, minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _unix_minus(hours: int = 0, minutes: int = 0) -> str:
    """Return a Unix timestamp string offset from now."""
    dt = datetime.now(UTC) - timedelta(hours=hours, minutes=minutes)
    return str(dt.timestamp())


def _build_alert_payloads() -> list[tuple[str, dict]]:
    """
    Build sample alert payloads for each source type.

    Returns a list of (source_name, raw_payload) tuples.
    Timestamps are relative to now so demo data always looks fresh.
    """
    return [
        # --- Sentinel alerts ---
        (
            "sentinel",
            {
                "id": "/subscriptions/demo/providers/Microsoft.SecurityInsights/incidents/demo-001",
                "name": "demo-001",
                "type": "Microsoft.SecurityInsights/incidents",
                "properties": {
                    "title": "Suspicious PowerShell Execution on WORKSTATION-01",
                    "description": (
                        "Multiple PowerShell commands with encoded arguments were executed "
                        "on WORKSTATION-01 by user jdoe@contoso.com. The process connected "
                        "to a known C2 IP address."
                    ),
                    "severity": "High",
                    "status": "New",
                    "createdTimeUtc": _now_minus(hours=2),
                    "firstActivityTimeUtc": _now_minus(hours=2, minutes=10),
                    "lastActivityTimeUtc": _now_minus(hours=2),
                    "incidentNumber": 10001,
                    "relatedAnalyticRuleIds": [
                        "/subscriptions/demo/alertRules/rule-uuid-abc123"
                    ],
                    "labels": [
                        {"labelName": "powershell", "labelType": "User"},
                        {"labelName": "endpoint", "labelType": "AutoAssigned"},
                    ],
                    "additionalData": {
                        "alertsCount": 2,
                        "tactics": ["Execution", "DefenseEvasion"],
                    },
                },
                "Entities": [
                    {"Type": "ip", "Address": "10.0.0.55"},
                    {"Type": "ip", "Address": "185.220.101.32"},
                    {"Type": "account", "Name": "jdoe", "UPNSuffix": "contoso.com"},
                    {"Type": "host", "HostName": "WORKSTATION-01", "DnsDomain": "contoso.com"},
                    {
                        "Type": "filehash",
                        "Algorithm": "SHA256",
                        "Value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    },
                ],
            },
        ),
        (
            "sentinel",
            {
                "id": "/subscriptions/demo/providers/Microsoft.SecurityInsights/incidents/demo-002",
                "name": "demo-002",
                "type": "Microsoft.SecurityInsights/incidents",
                "properties": {
                    "title": "Impossible Travel — Sign-in from US and Romania within 15 minutes",
                    "description": (
                        "User admin@contoso.com signed in from New York, US and Bucharest, Romania "
                        "within 15 minutes. The sign-in from Romania used a new device and browser."
                    ),
                    "severity": "Medium",
                    "status": "New",
                    "createdTimeUtc": _now_minus(hours=1),
                    "firstActivityTimeUtc": _now_minus(hours=1, minutes=20),
                    "lastActivityTimeUtc": _now_minus(hours=1, minutes=5),
                    "incidentNumber": 10002,
                    "relatedAnalyticRuleIds": [
                        "/subscriptions/demo/alertRules/rule-uuid-impossible-travel"
                    ],
                    "labels": [
                        {"labelName": "identity", "labelType": "User"},
                        {"labelName": "impossible-travel", "labelType": "AutoAssigned"},
                    ],
                    "additionalData": {
                        "alertsCount": 1,
                        "tactics": ["InitialAccess"],
                    },
                },
                "Entities": [
                    {"Type": "ip", "Address": "203.0.113.10"},
                    {"Type": "ip", "Address": "198.51.100.45"},
                    {"Type": "account", "Name": "admin", "UPNSuffix": "contoso.com"},
                ],
            },
        ),
        (
            "sentinel",
            {
                "id": "/subscriptions/demo/providers/Microsoft.SecurityInsights/incidents/demo-003",
                "name": "demo-003",
                "type": "Microsoft.SecurityInsights/incidents",
                "properties": {
                    "title": "Sign-in from TOR Exit Node",
                    "description": (
                        "User svc-backup@contoso.com signed in from a known TOR exit node. "
                        "This service account should not be used interactively."
                    ),
                    "severity": "High",
                    "status": "New",
                    "createdTimeUtc": _now_minus(minutes=45),
                    "firstActivityTimeUtc": _now_minus(minutes=50),
                    "lastActivityTimeUtc": _now_minus(minutes=45),
                    "incidentNumber": 10003,
                    "relatedAnalyticRuleIds": [
                        "/subscriptions/demo/alertRules/rule-uuid-abc123"
                    ],
                    "labels": [
                        {"labelName": "tor", "labelType": "AutoAssigned"},
                        {"labelName": "identity", "labelType": "User"},
                    ],
                    "additionalData": {
                        "alertsCount": 1,
                        "tactics": ["InitialAccess"],
                    },
                },
                "Entities": [
                    {"Type": "ip", "Address": "185.220.101.1"},
                    {"Type": "account", "Name": "svc-backup", "UPNSuffix": "contoso.com"},
                ],
            },
        ),
        # --- Elastic alerts ---
        (
            "elastic",
            {
                "@timestamp": _now_minus(hours=3),
                "kibana.alert.uuid": "demo-elastic-001",
                "kibana.alert.rule.uuid": "rule-uuid-elastic-malware",
                "kibana.alert.rule.name": "Malware Hash Match — Endpoint",
                "kibana.alert.rule.description": "File hash matches known malware signature",
                "kibana.alert.rule.severity": "critical",
                "kibana.alert.rule.risk_score": 95,
                "kibana.alert.rule.tags": ["Malware", "Endpoint", "T1204.002"],
                "kibana.alert.severity": "critical",
                "kibana.alert.start": _now_minus(hours=3, minutes=5),
                "kibana.alert.workflow_status": "open",
                "kibana.alert.reason": (
                    "File with known malicious hash was executed on SERVER-DB-01"
                ),
                "host.name": "SERVER-DB-01",
                "host.ip": ["10.0.1.20"],
                "source.ip": "10.0.1.20",
                "user.name": "dbadmin",
                "user.email": "dbadmin@contoso.com",
                "process.name": "update_service.exe",
                "process.executable": "C:\\ProgramData\\Temp\\update_service.exe",
                "process.hash.sha256": (
                    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
                ),
                "process.hash.md5": "098f6bcd4621d373cade4e832627b4f6",
                "destination.ip": "45.33.32.156",
                "destination.domain": "malware-c2.evil.example.com",
            },
        ),
        (
            "elastic",
            {
                "@timestamp": _now_minus(hours=1, minutes=30),
                "kibana.alert.uuid": "demo-elastic-002",
                "kibana.alert.rule.uuid": "rule-uuid-elastic-cred-dump",
                "kibana.alert.rule.name": "Credential Dumping via LSASS Access",
                "kibana.alert.rule.description": (
                    "Process accessed LSASS memory, possible credential dumping"
                ),
                "kibana.alert.rule.severity": "high",
                "kibana.alert.rule.risk_score": 85,
                "kibana.alert.rule.tags": ["Credential Access", "T1003.001", "Endpoint"],
                "kibana.alert.severity": "high",
                "kibana.alert.start": _now_minus(hours=1, minutes=35),
                "kibana.alert.workflow_status": "open",
                "kibana.alert.reason": "rundll32.exe accessed lsass.exe memory on WORKSTATION-05",
                "host.name": "WORKSTATION-05",
                "host.ip": ["10.0.0.105"],
                "source.ip": "10.0.0.105",
                "user.name": "itadmin",
                "user.email": "itadmin@contoso.com",
                "process.name": "rundll32.exe",
                "process.executable": "C:\\Windows\\System32\\rundll32.exe",
                "process.hash.sha256": (
                    "7b502c3a1f48c8609ae212cdfb639dee39673f5e36b6b1be8a3e9ba29af3d2a4"
                ),
            },
        ),
        (
            "elastic",
            {
                "@timestamp": _now_minus(minutes=20),
                "kibana.alert.uuid": "demo-elastic-003",
                "kibana.alert.rule.uuid": "rule-uuid-elastic-susp-proc",
                "kibana.alert.rule.name": "Suspicious Process — Certutil Download",
                "kibana.alert.rule.description": (
                    "certutil.exe used to download a file from the internet"
                ),
                "kibana.alert.rule.severity": "medium",
                "kibana.alert.rule.risk_score": 55,
                "kibana.alert.rule.tags": ["Defense Evasion", "T1140", "Endpoint"],
                "kibana.alert.severity": "medium",
                "kibana.alert.start": _now_minus(minutes=25),
                "kibana.alert.workflow_status": "open",
                "kibana.alert.reason": (
                    "certutil.exe downloaded payload from external URL "
                    "on WORKSTATION-03"
                ),
                "host.name": "WORKSTATION-03",
                "host.ip": ["10.0.0.80"],
                "source.ip": "10.0.0.80",
                "destination.ip": "93.184.216.34",
                "destination.domain": "downloads.suspicious-site.example.com",
                "url.full": "https://downloads.suspicious-site.example.com/payload.bin",
                "user.name": "jsmith",
                "user.email": "jsmith@contoso.com",
                "process.name": "certutil.exe",
                "process.executable": "C:\\Windows\\System32\\certutil.exe",
                "dns.question.name": "downloads.suspicious-site.example.com",
            },
        ),
        # --- Splunk alerts ---
        (
            "splunk",
            {
                "result": {
                    "_time": _unix_minus(hours=4),
                    "rule_name": "Brute Force Login Attempt",
                    "rule_description": "More than 10 failed logins from a single IP in 5 minutes",
                    "signature": "Brute Force Attack Detected",
                    "severity": "high",
                    "urgency": "high",
                    "src_ip": "192.0.2.100",
                    "dest_ip": "10.0.1.5",
                    "user": "svc-sql@contoso.com",
                    "sha256": "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
                    "domain": "contoso.com",
                    "mitre_attack_id": "T1110.001",
                },
                "sid": "scheduler__admin__brute_force_demo_001",
                "results_link": "https://splunk.contoso.com/app/ES/incidents",
                "search_name": "Brute Force Login Attempt",
            },
        ),
        (
            "splunk",
            {
                "result": {
                    "_time": _unix_minus(hours=1, minutes=15),
                    "rule_name": "DNS Tunneling Exfiltration",
                    "rule_description": (
                        "High-entropy DNS queries indicating "
                        "possible DNS tunneling"
                    ),
                    "signature": "DNS Tunneling Detected",
                    "severity": "critical",
                    "urgency": "critical",
                    "src_ip": "10.0.0.200",
                    "dest_ip": "8.8.8.8",
                    "user": "workstation$",
                    "domain": "aGVsbG8ud29ybGQ.exfil.evil.example.com",
                    "mitre_attack_id": "T1048.003",
                },
                "sid": "scheduler__admin__dns_tunnel_demo_001",
                "results_link": "https://splunk.contoso.com/app/ES/incidents",
                "search_name": "DNS Tunneling Exfiltration",
            },
        ),
        (
            "splunk",
            {
                "result": {
                    "_time": _unix_minus(minutes=40),
                    "rule_name": "Anomalous Outbound Data Transfer",
                    "rule_description": "Host transferred > 500MB to external IP in 1 hour",
                    "signature": "Large Outbound Transfer",
                    "severity": "high",
                    "urgency": "high",
                    "src_ip": "10.0.0.150",
                    "dest_ip": "104.18.32.7",
                    "user": "finance-user@contoso.com",
                    "domain": "file-share.suspicious.example.com",
                    "url": "https://file-share.suspicious.example.com/upload",
                    "mitre_attack_id": "T1048",
                },
                "sid": "scheduler__admin__outbound_transfer_demo_001",
                "results_link": "https://splunk.contoso.com/app/ES/incidents",
                "search_name": "Anomalous Outbound Data Transfer",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Source plugin registry
# ---------------------------------------------------------------------------

_SOURCES = {
    "sentinel": SentinelSource(),
    "elastic": ElasticSource(),
    "splunk": SplunkSource(),
}


# ---------------------------------------------------------------------------
# Seeder logic
# ---------------------------------------------------------------------------


async def _seed_detection_rules(session) -> int:  # type: ignore[no-untyped-def]
    """Create detection rules. Returns count of rules created."""
    repo = DetectionRuleRepository(session)
    created = 0
    for rule_data in DETECTION_RULES:
        existing = await repo.get_by_source_rule_id(
            rule_data["source_name"], rule_data["source_rule_id"]
        )
        if existing:
            logger.info(
                "detection_rule_exists",
                name=rule_data["name"],
                uuid=str(existing.uuid),
            )
            continue

        rule = await repo.create(DetectionRuleCreate(**rule_data))
        created += 1
        logger.info(
            "detection_rule_created",
            name=rule.name,
            uuid=str(rule.uuid),
        )
    return created



async def _seed_alerts(
    session: AsyncSession, queue: TaskQueueBase
) -> int:
    """Ingest sample alerts through the standard pipeline. Returns count."""
    ingest_service = AlertIngestionService(session, queue)
    payloads = _build_alert_payloads()
    created = 0
    for source_name, raw_payload in payloads:
        source = _SOURCES[source_name]
        result = await ingest_service.ingest(
            source,
            raw_payload,
            actor_type="system",
        )
        created += 1
        logger.info(
            "demo_alert_ingested",
            alert_uuid=str(result.alert.uuid),
            source_name=source_name,
            title=result.alert.title,
            is_duplicate=result.is_duplicate,
        )
    return created


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the Calseta database with realistic demo data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m app.cli.seed_demo_data\n"
            "  python -m app.cli.seed_demo_data --skip-alerts\n"
            "  python -m app.cli.seed_demo_data --skip-enrichment\n"
        ),
    )
    parser.add_argument(
        "--skip-alerts",
        action="store_true",
        help="Only create detection rules and context documents; skip alert ingest.",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Ingest alerts but do not enqueue enrichment tasks.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    from app.queue.factory import get_queue_backend

    async with AsyncSessionLocal() as session:
        # --- Detection Rules ---
        rules_created = await _seed_detection_rules(session)

        # --- Alerts ---
        alerts_created = 0
        if not args.skip_alerts:
            if args.skip_enrichment:
                queue: TaskQueueBase = _NoOpQueue()
            else:
                queue = get_queue_backend()
            alerts_created = await _seed_alerts(session, queue)

        await session.commit()

    print()
    print("Demo data seeded successfully.")
    print()
    print(f"  Detection rules created: {rules_created}")
    if args.skip_alerts:
        print("  Alerts: skipped (--skip-alerts)")
    else:
        print(f"  Alerts ingested: {alerts_created}")
        if args.skip_enrichment:
            print("  Enrichment: skipped (--skip-enrichment)")
        else:
            print("  Enrichment: enqueued (run the worker to process)")
    print()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logger.error("seed_demo_data_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
