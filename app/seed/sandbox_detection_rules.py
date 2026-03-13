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
    mitre_subtechniques: list[str]
    data_sources: list[str]
    run_frequency: str
    created_by: str
    documentation: str


_DOC_BRUTE_FORCE_TOR = """\
# Brute Force Sign-In Attempts from TOR Network - v1

## Overview

> Detects multiple failed sign-in attempts originating from known TOR exit \
nodes targeting Entra ID accounts. TOR-based brute force is a strong indicator \
of credential stuffing or targeted account compromise, as attackers use TOR to \
evade IP-based blocking and rate limiting.

---

## Metadata

* **ID:** `c9a7e4d2-3b1f-4e8a-9c6d-f0123456789a`
* **Enabled:** `yes`
* **Created By:** `soc.engineering@contoso.com`
* **Runs Every:** `5 mins`
* **Severity:** `high`

---

## Query

```kql
SigninLogs
| where ResultType != 0
| extend IPCategory = iff(IPAddress in (externaldata(ip:string) \
[@"https://check.torproject.org/torbulkexitlist"]), "TOR", "Other")
| where IPCategory == "TOR"
| summarize FailureCount = count(), TargetAccounts = dcount(UserPrincipalName), \
earliest = min(TimeGenerated), latest = max(TimeGenerated) by IPAddress
| where FailureCount >= 5
| where datetime_diff('minute', latest, earliest) <= 10
```

---

## Threshold *(optional)*

* **Field:** `FailureCount`
* **Threshold:** `>= 5 failures within 10 minutes from a single TOR IP`

---

## Alert Suppression *(optional)*

* **Suppression Field:** `IPAddress`
* **Suppression Duration:** `30m`

---

## Machine Learning Job *(optional)*

> Not applicable for this rule.

---

## MITRE ATT&CK

* **Tactics:** `Initial Access`, `Credential Access`
* **Techniques:** `T1110 - Brute Force`
* **Sub-Techniques:** `T1110.001 - Password Guessing`, `T1110.003 - Password Spraying`

---

## Goal

> Detect and alert on brute force authentication attempts originating from \
TOR exit nodes before account compromise occurs.

---

## Strategy Abstract

> This rule correlates failed sign-in events with a curated TOR exit node \
feed. It triggers when a single TOR IP generates 5+ authentication failures \
within a 10-minute window. The use of TOR for brute force indicates deliberate \
evasion of network-level controls and is rarely legitimate.

---

## Data Sources

* `Entra ID Sign-In Logs`
* `TOR Exit Node Bulk Exit List`

---

## Blind Spots & Assumptions

* Relies on an up-to-date TOR exit node list; new nodes may not be indexed.
* Does not detect attacks from non-TOR anonymizing proxies or VPNs.
* Assumes sign-in logs are ingested with < 5 minute latency.

---

## False Positives

* Security researchers testing from TOR.
* Penetration testing engagements using TOR egress.
* Legitimate users in restrictive countries using TOR for privacy.

---

## Validation

> Simulate by generating 5+ failed sign-in attempts from a known TOR exit \
node IP within 10 minutes. Verify the alert fires and the source IP is \
correctly tagged.

---

## Priority

> High - TOR-based brute force indicates deliberate evasion and targeted \
credential attacks.

---

## Responses

* Verify the target account(s) for any successful sign-ins from the TOR IP.
* Check if the TOR IP has attempted other accounts (password spraying).
* Block the IP range via Conditional Access or firewall.
* If any account was compromised: suspend, revoke sessions, reset password.
* Review MFA enrollment status of targeted accounts.

---

## Additional Notes

* Combine with Impossible Travel and Anomalous Sign-In Location rules.
* Consider creating a Conditional Access policy to block TOR by default.
* Related playbook: `Identity Compromise Investigation Runbook`.
"""

_DOC_MALWARE_HASH = """\
# Known Malware Hash Detected on Endpoint - v1

## Overview

> Triggers when a file with a hash matching known malware signatures is \
detected on an endpoint. This indicates active malware presence and requires \
immediate host isolation and forensic investigation.

---

## Metadata

* **ID:** `d8e5f6a7-b9c0-4d1e-a2f3-456789abcdef`
* **Enabled:** `yes`
* **Created By:** `threat.intel@contoso.com`
* **Runs Every:** `1 min`
* **Severity:** `critical`

---

## Query

```eql
file where event.action == "creation" and
  file.hash.sha256 in ("known_malware_hashes_list")
```

---

## Threshold *(optional)*

* **Field:** `file.hash.sha256`
* **Threshold:** `Any match against the threat intelligence hash feed`

---

## Alert Suppression *(optional)*

* **Suppression Field:** `host.name + file.hash.sha256`
* **Suppression Duration:** `1h`

---

## Machine Learning Job *(optional)*

> Not applicable — this is a signature-based detection.

---

## MITRE ATT&CK

* **Tactics:** `Execution`
* **Techniques:** `T1204 - User Execution`
* **Sub-Techniques:** `T1204.002 - Malicious File`

---

## Goal

> Detect known malware on endpoints at the earliest possible stage to \
prevent lateral movement, data exfiltration, or further compromise.

---

## Strategy Abstract

> This rule compares file hashes observed on endpoints against a curated \
threat intelligence feed of known malware signatures. It fires on any exact \
hash match (MD5, SHA1, or SHA256). The 1-minute run frequency ensures near \
real-time detection of known threats.

---

## Data Sources

* `Endpoint File Creation Events (Elastic Agent)`
* `EDR Telemetry`
* `Threat Intelligence Hash Feeds`

---

## Blind Spots & Assumptions

* Cannot detect unknown/zero-day malware (no hash in the feed).
* Packed, polymorphic, or fileless malware will evade hash-based detection.
* Assumes EDR agent is running and reporting file events.

---

## False Positives

* Legitimate security tools that contain malware samples (e.g., AV test files).
* EICAR test files used for AV validation.
* Hash collisions (extremely rare with SHA256).

---

## Validation

> Drop a known test malware hash (EICAR) on a monitored endpoint. Verify \
the alert fires within 2 minutes and the hash, hostname, and user are \
correctly captured.

---

## Priority

> Critical - Known malware on an endpoint is an active threat requiring \
immediate containment.

---

## Responses

* Immediately isolate the affected host via the EDR agent.
* Collect a memory dump and volatile artifacts before remediation.
* Verify the hash against VirusTotal for malware family and C2 domains.
* Check for lateral movement: same hash on other hosts in the last 7 days.
* Identify the delivery vector (email attachment, download, USB).
* Block extracted C2 domains/IPs at the firewall.

---

## Additional Notes

* Pair with behavioral detection rules for defense-in-depth.
* Ensure the threat intel hash feed is updated at least daily.
* Related playbook: `Malware Detection and Containment SOP`.
"""

_DOC_DATA_TRANSFER = """\
# Anomalous Large Data Transfer to External Destination - v1

## Overview

> Detects data transfers that significantly exceed baseline thresholds to \
external destinations. Large outbound transfers to unfamiliar or low-reputation \
destinations may indicate data exfiltration by a compromised account, insider \
threat, or malware beaconing with bulk data upload.

---

## Metadata

* **ID:** `Anomalous Outbound Data Transfer`
* **Enabled:** `yes`
* **Created By:** `soc.engineering@contoso.com`
* **Runs Every:** `15 mins`
* **Severity:** `high`

---

## Query

```spl
index=firewall sourcetype=fw_traffic action=allowed direction=outbound
| stats sum(bytes_out) as total_bytes, dc(dest_ip) as unique_dests, \
values(app) as apps by src_ip, user
| where total_bytes > 1073741824
| eval total_gb = round(total_bytes/1073741824, 2)
| where unique_dests < 5
| table _time, user, src_ip, total_gb, unique_dests, apps
```

---

## Threshold *(optional)*

* **Field:** `bytes_out`
* **Threshold:** `> 1 GB to external destinations within the run window`

---

## Alert Suppression *(optional)*

* **Suppression Field:** `src_ip + user`
* **Suppression Duration:** `2h`

---

## Machine Learning Job *(optional)*

> Consider pairing with a Splunk MLTK baseline model for per-user transfer \
volume anomaly detection.

---

## MITRE ATT&CK

* **Tactics:** `Exfiltration`
* **Techniques:** `T1048 - Exfiltration Over Alternative Protocol`
* **Sub-Techniques:** `T1048.001 - Exfiltration Over Symmetric Encrypted \
Non-C2 Protocol`

---

## Goal

> Identify anomalous large data transfers to external destinations that may \
indicate data exfiltration or unauthorized data movement.

---

## Strategy Abstract

> This rule aggregates outbound traffic volume per source IP and user, \
triggering when total bytes exceed 1 GB within the 15-minute run window. It \
focuses on transfers to a small number of unique destinations (< 5), which is \
characteristic of targeted exfiltration rather than normal browsing.

---

## Data Sources

* `Firewall Logs`
* `Web Proxy Logs`
* `NetFlow / sFlow Records`

---

## Blind Spots & Assumptions

* Encrypted traffic (TLS) volume is visible but content is not inspectable.
* Cloud storage uploads via browser may be categorized as web traffic.
* Assumes firewall logs capture byte counts accurately.
* Does not detect slow-and-low exfiltration below the 1 GB threshold.

---

## False Positives

* Legitimate large file uploads to cloud storage (OneDrive, Google Drive).
* Backup services or replication jobs.
* Software update distribution from internal servers.
* Video conferencing with screen sharing.

---

## Validation

> Generate a 1.5 GB file transfer to an external test server. Verify the \
alert fires within 15 minutes and captures the correct user, source IP, and \
byte count.

---

## Priority

> High - Large outbound transfers to few destinations suggest targeted \
exfiltration.

---

## Responses

* Identify the user and determine if the transfer was authorized.
* Check the destination IP/domain reputation via threat intelligence.
* Review DLP alerts for the same user and time window.
* Inspect the transfer protocol and application (custom_sync.exe is suspicious).
* Compare transfer volume against the user's 30-day baseline.
* If confirmed exfiltration: block destination, preserve logs, escalate to IR.

---

## Additional Notes

* Pair with DLP policy alerts for content-aware detection.
* Service accounts (e.g., `svc_backup`) should be baselined separately.
* Related playbook: `Data Exfiltration Investigation Plan`.
"""

_DOC_IMPOSSIBLE_TRAVEL = """\
# Impossible Travel Activity Detected - v1

## Overview

> Detects authentication events from geographically distant locations within \
an impossibly short timeframe. This pattern strongly suggests credential \
compromise, session hijacking, or token theft, as no human can physically \
travel between the locations in the observed time.

---

## Metadata

* **ID:** `e7f8a9b0-c1d2-4e3f-a5b6-c7d8e9f01234`
* **Enabled:** `yes`
* **Created By:** `identity.security@contoso.com`
* **Runs Every:** `5 mins`
* **Severity:** `high`

---

## Query

```kql
SigninLogs
| where ResultType == 0
| extend City = tostring(LocationDetails.city), \
Country = tostring(LocationDetails.countryOrRegion), \
Lat = todouble(LocationDetails.geoCoordinates.latitude), \
Lon = todouble(LocationDetails.geoCoordinates.longitude)
| summarize Locations = make_set(pack("city", City, "country", Country, \
"lat", Lat, "lon", Lon, "time", TimeGenerated)) by UserPrincipalName
| mv-expand L1 = Locations, L2 = Locations
| where L1.time < L2.time
| extend distance_km = geo_distance_2points(L1.lon, L1.lat, L2.lon, L2.lat) \
/ 1000
| extend time_diff_min = datetime_diff('minute', todatetime(L2.time), \
todatetime(L1.time))
| where distance_km > 500 and time_diff_min < 60
```

---

## Threshold *(optional)*

* **Field:** `distance_km / time_diff_min`
* **Threshold:** `> 500 km apart with < 60 minutes between sign-ins`

---

## Alert Suppression *(optional)*

* **Suppression Field:** `UserPrincipalName`
* **Suppression Duration:** `1h`

---

## Machine Learning Job *(optional)*

> Entra ID Protection has a built-in impossible travel ML model. This rule \
serves as a complementary deterministic detection.

---

## MITRE ATT&CK

* **Tactics:** `Initial Access`
* **Techniques:** `T1078 - Valid Accounts`
* **Sub-Techniques:** `T1078.004 - Cloud Accounts`

---

## Goal

> Identify account compromise by detecting physically impossible \
authentication patterns across geographic locations.

---

## Strategy Abstract

> This rule calculates the geographic distance between consecutive successful \
sign-in events for the same user. If two sign-ins occur more than 500 km apart \
within 60 minutes, the travel is flagged as impossible. The rule assumes \
accurate IP geolocation and uses the Haversine formula for distance calculation.

---

## Data Sources

* `Entra ID Sign-In Logs`
* `Geo-IP Database`

---

## Blind Spots & Assumptions

* VPN and proxy usage can cause legitimate sign-ins to appear geographically \
distant.
* IP geolocation accuracy varies; some IPs may be mislocated.
* Does not account for delegated authentication or token replay from a \
different location.

---

## False Positives

* Users connecting via corporate VPN (VPN egress in different country).
* Cloud proxy services (Zscaler, Netskope) with distributed PoPs.
* Shared accounts used by team members in different locations.
* Mobile users switching between Wi-Fi and cellular (different geo-IP).

---

## Validation

> Simulate by signing into an account from two IPs geolocated > 500 km \
apart within a 30-minute window. Verify the alert fires with correct \
location details.

---

## Priority

> High - Impossible travel is a strong indicator of credential compromise, \
especially for privileged accounts.

---

## Responses

* Verify the user's actual location and recent travel schedule.
* Check if a VPN or proxy could explain the geographic discrepancy.
* Review device fingerprints for both sign-in events.
* If the account is privileged (Global Admin, etc.): immediately suspend.
* Revoke active sessions and force re-authentication with MFA.
* Check for post-compromise activity: new inbox rules, app consent grants.

---

## Additional Notes

* High-privilege accounts (Global Admin, Exchange Admin) should trigger \
P1 escalation regardless of VPN status.
* Combine with Brute Force and Anomalous Sign-In Location rules.
* Related playbook: `Identity Compromise Investigation Runbook`.
"""

_DOC_POWERSHELL_ENCODED = """\
# Suspicious PowerShell Execution with Encoded Command - v1

## Overview

> Detects PowerShell execution using encoded commands combined with execution \
policy bypass and hidden window flags. This pattern is heavily used by \
attackers for initial payload delivery, C2 communication, and defense evasion. \
Legitimate use of `-EncodedCommand` is rare in enterprise environments.

---

## Metadata

* **ID:** `a9b0c1d2-e3f4-5678-9abc-def012345678`
* **Enabled:** `yes`
* **Created By:** `threat.detection@contoso.com`
* **Runs Every:** `1 min`
* **Severity:** `high`

---

## Query

```eql
process where event.type == "start" and
  process.name == "powershell.exe" and
  process.args : ("-enc*", "-EncodedCommand*") and
  process.args : ("-ExecutionPolicy*Bypass*", "-ep*bypass*") and
  process.args : ("-WindowStyle*Hidden*", "-w*hidden*")
```

---

## Threshold *(optional)*

* **Field:** `process.args`
* **Threshold:** `Any match with encoded command + bypass + hidden window`

---

## Alert Suppression *(optional)*

* **Suppression Field:** `host.name + process.parent.name`
* **Suppression Duration:** `15m`

---

## Machine Learning Job *(optional)*

> Consider pairing with a PowerShell script block anomaly model to detect \
novel encoded payloads.

---

## MITRE ATT&CK

* **Tactics:** `Execution`, `Defense Evasion`
* **Techniques:** `T1059.001 - PowerShell`, `T1027 - Obfuscated Files or \
Information`
* **Sub-Techniques:** `T1059.001 - PowerShell`, `T1027.010 - Command \
Obfuscation`

---

## Goal

> Detect attacker use of encoded PowerShell commands for payload delivery, \
C2 communication, and defense evasion before lateral movement occurs.

---

## Strategy Abstract

> This rule monitors process creation events for powershell.exe invocations \
that combine three suspicious flags: encoded command input, execution policy \
bypass, and hidden window mode. The combination of all three is a strong \
indicator of malicious activity, as legitimate scripts rarely need to hide \
their execution window while bypassing security policies.

---

## Data Sources

* `Process Creation Events (Elastic Agent / Sysmon)`
* `PowerShell Script Block Logging (Event ID 4104)`
* `Windows Security Event Log (Event ID 4688)`

---

## Blind Spots & Assumptions

* Does not detect PowerShell executed via `pwsh.exe` (PowerShell 7+).
* Cannot detect encoded commands passed via environment variables or files.
* Assumes process argument logging is enabled and complete.
* Fileless attacks using .NET reflection may bypass process-level detection.

---

## False Positives

* SCCM/Intune deployment scripts that use encoded commands.
* Legitimate automation tools (e.g., Ansible WinRM modules).
* Security tools performing remediation actions.

---

## Validation

> Execute a benign encoded PowerShell command with bypass and hidden flags \
on a test endpoint:
> ```powershell
> powershell -EncodedCommand dABlAHMAdAA= -ExecutionPolicy Bypass \
-WindowStyle Hidden
> ```
> Verify the alert fires within 2 minutes with correct process tree details.

---

## Priority

> High - Encoded PowerShell with evasion flags is a strong indicator of \
active compromise or payload delivery.

---

## Responses

* Decode the base64 encoded command to identify the payload.
* Inspect the parent process chain for initial access vector.
* Check destination domains/IPs extracted from the decoded command for C2.
* Isolate the host if C2 communication is confirmed.
* Search for the same encoded command or parent process across all endpoints.
* Collect PowerShell script block logs (Event ID 4104) for full execution trace.

---

## Additional Notes

* Always decode the base64 payload before making a severity determination.
* Pair with network detection rules for C2 domain/IP correlation.
* Related playbook: `Malware Detection and Containment SOP`.
"""

_SANDBOX_RULES: list[_RuleSpec] = [
    _RuleSpec(
        name="Brute Force Sign-In Attempts from TOR Network",
        source_name="sentinel",
        source_rule_id="c9a7e4d2-3b1f-4e8a-9c6d-f0123456789a",
        severity="High",
        mitre_tactics=["InitialAccess", "CredentialAccess"],
        mitre_techniques=["T1110", "T1110.001"],
        mitre_subtechniques=["T1110.001", "T1110.003"],
        data_sources=["Azure AD Sign-in Logs", "TOR Exit Node Feed"],
        run_frequency="5m",
        created_by="soc.engineering@contoso.com",
        documentation=_DOC_BRUTE_FORCE_TOR,
    ),
    _RuleSpec(
        name="Known Malware Hash Detected on Endpoint",
        source_name="elastic",
        source_rule_id="d8e5f6a7-b9c0-4d1e-a2f3-456789abcdef",
        severity="Critical",
        mitre_tactics=["Execution"],
        mitre_techniques=["T1204", "T1204.002"],
        mitre_subtechniques=["T1204.002"],
        data_sources=["Endpoint File Creation Events", "EDR Telemetry"],
        run_frequency="1m",
        created_by="threat.intel@contoso.com",
        documentation=_DOC_MALWARE_HASH,
    ),
    _RuleSpec(
        name="Anomalous Large Data Transfer to External Destination",
        source_name="splunk",
        source_rule_id="Anomalous Outbound Data Transfer",
        severity="High",
        mitre_tactics=["Exfiltration"],
        mitre_techniques=["T1048", "T1048.001"],
        mitre_subtechniques=["T1048.001"],
        data_sources=["Firewall Logs", "Proxy Logs", "NetFlow"],
        run_frequency="15m",
        created_by="soc.engineering@contoso.com",
        documentation=_DOC_DATA_TRANSFER,
    ),
    _RuleSpec(
        name="Impossible Travel Activity Detected",
        source_name="sentinel",
        source_rule_id="e7f8a9b0-c1d2-4e3f-a5b6-c7d8e9f01234",
        severity="High",
        mitre_tactics=["InitialAccess"],
        mitre_techniques=["T1078", "T1078.004"],
        mitre_subtechniques=["T1078.004"],
        data_sources=["Azure AD Sign-in Logs", "Geo-IP Database"],
        run_frequency="5m",
        created_by="identity.security@contoso.com",
        documentation=_DOC_IMPOSSIBLE_TRAVEL,
    ),
    _RuleSpec(
        name="Suspicious PowerShell Execution with Encoded Command",
        source_name="elastic",
        source_rule_id="a9b0c1d2-e3f4-5678-9abc-def012345678",
        severity="High",
        mitre_tactics=["Execution", "DefenseEvasion"],
        mitre_techniques=["T1059.001", "T1027"],
        mitre_subtechniques=["T1059.001", "T1027.010"],
        data_sources=["Process Creation Events", "PowerShell Script Block Logging"],
        run_frequency="1m",
        created_by="threat.detection@contoso.com",
        documentation=_DOC_POWERSHELL_ENCODED,
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
            mitre_subtechniques=spec.mitre_subtechniques,
            data_sources=spec.data_sources,
            run_frequency=spec.run_frequency,
            created_by=spec.created_by,
            documentation=spec.documentation,
        )
        db.add(rule)
        created.append(rule)

    if created:
        await db.flush()
        logger.info("sandbox_detection_rules_seeded", count=len(created))

    return created
