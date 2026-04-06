"""
Control plane lab seeder — LLM integrations, agents, issues, routines, KB pages.

Called from seed_sandbox() when SANDBOX_MODE=true.
Idempotent: every sub-seeder checks before inserting.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import bcrypt
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_api_key import AgentAPIKey
from app.db.models.agent_issue import AgentIssue
from app.db.models.agent_registration import AgentRegistration
from app.db.models.agent_routine import AgentRoutine
from app.db.models.kb_page import KnowledgeBasePage
from app.db.models.llm_integration import LLMIntegration
from app.db.models.routine_trigger import RoutineTrigger

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Integration
# ---------------------------------------------------------------------------

_LLM_INTEGRATION_NAME = "claude-code-local"


async def _seed_llm_integration(db: AsyncSession) -> LLMIntegration:
    """Seed the Claude Code local LLM integration. Idempotent."""
    existing = await db.execute(
        select(LLMIntegration).where(LLMIntegration.name == _LLM_INTEGRATION_NAME)
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    integration = LLMIntegration(
        name=_LLM_INTEGRATION_NAME,
        provider="claude_code",
        model="claude-sonnet-4-6",
        api_key_ref=None,
        config={"max_tokens": 8096},
        cost_per_1k_input_tokens_cents=0,
        cost_per_1k_output_tokens_cents=0,
        is_default=True,
    )
    db.add(integration)
    await db.flush()
    logger.info("lab_llm_integration_seeded", name=_LLM_INTEGRATION_NAME)
    return integration


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

_AGENT_SCOPES = [
    "alerts:read",
    "alerts:write",
    "enrichments:read",
    "workflows:read",
    "workflows:execute",
    "agents:read",
]

_AGENT_SPECS = [
    {
        "name": "lead-investigator",
        "description": "Orchestrates specialist sub-agents to produce comprehensive investigation findings",
        "execution_mode": "managed",
        "agent_type": "orchestrator",
        "role": "investigation",
        "status": "active",
        "adapter_type": "http",
        "system_prompt": (
            "You are a senior SOC analyst and lead investigator. "
            "Your job is to coordinate specialist agents, synthesize their findings, "
            "and produce a clear verdict with confidence-scored response recommendations. "
            "Always ground conclusions in evidence from enriched indicators and alert context."
        ),
        "methodology": (
            "1. Review alert and enriched indicators\n"
            "2. Identify which specialists to invoke based on indicator types\n"
            "3. Delegate to specialists in parallel\n"
            "4. Synthesize findings into a verdict\n"
            "5. Propose response actions with confidence scores"
        ),
        "capabilities": {
            "can_invoke": [
                "threat-intel-analyst",
                "identity-analyst",
                "historical-context-analyst",
            ],
            "alert_types": ["*"],
            "tools": [
                "get_alert",
                "search_alerts",
                "post_finding",
                "propose_action",
                "delegate_task",
            ],
        },
        "trigger_on_severities": ["High", "Critical"],
        "max_concurrent_alerts": 3,
        "max_sub_agent_calls": 10,
        "budget_monthly_cents": 0,
    },
    {
        "name": "threat-intel-analyst",
        "description": "Deep-dives on IOCs beyond built-in enrichment",
        "execution_mode": "managed",
        "agent_type": "specialist",
        "role": "enrichment",
        "status": "active",
        "adapter_type": "http",
        "system_prompt": (
            "You are a threat intelligence analyst specializing in IOC analysis. "
            "You evaluate indicators using enrichment data, historical patterns, and threat feeds "
            "to determine malice verdicts and attribution context."
        ),
        "capabilities": {
            "indicator_types": ["ip", "domain", "hash_md5", "hash_sha256", "url"],
            "tools": ["get_alert", "enrich_indicator", "search_alerts"],
        },
        "trigger_on_severities": [],
        "max_concurrent_alerts": 5,
        "max_sub_agent_calls": None,
        "budget_monthly_cents": 0,
    },
    {
        "name": "identity-analyst",
        "description": "Investigates user and account context for compromise indicators",
        "execution_mode": "managed",
        "agent_type": "specialist",
        "role": "investigation",
        "status": "active",
        "adapter_type": "http",
        "system_prompt": (
            "You are an identity security specialist. "
            "You investigate account activity, MFA status, impossible travel, and session anomalies "
            "to determine whether an account has been compromised."
        ),
        "capabilities": {
            "indicator_types": ["account", "email"],
            "tools": ["get_alert", "enrich_indicator"],
        },
        "trigger_on_severities": [],
        "max_concurrent_alerts": 5,
        "max_sub_agent_calls": None,
        "budget_monthly_cents": 0,
    },
    {
        "name": "historical-context-analyst",
        "description": "Searches prior alert history for recurrence patterns",
        "execution_mode": "managed",
        "agent_type": "specialist",
        "role": "investigation",
        "status": "active",
        "adapter_type": "http",
        "system_prompt": (
            "You are a SOC analyst specializing in historical alert correlation. "
            "You search prior alert history to identify recurrence patterns, "
            "known-benign sources, and escalating threat activity over time."
        ),
        "capabilities": {
            "tools": ["get_alert", "search_alerts"],
        },
        "trigger_on_severities": [],
        "max_concurrent_alerts": 5,
        "max_sub_agent_calls": None,
        "budget_monthly_cents": 0,
    },
]


def _agent_key_value(name: str) -> str:
    slug = name.replace("-", "_")
    return f"cak_lab_{slug}_key"


async def _seed_agent_api_key(
    db: AsyncSession, agent: AgentRegistration, key_value: str
) -> None:
    """Seed a cak_* agent API key if it doesn't already exist."""
    key_prefix = key_value[:8]
    existing = await db.execute(
        select(AgentAPIKey).where(
            AgentAPIKey.agent_registration_id == agent.id,
            AgentAPIKey.key_prefix == key_prefix,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    key_hash = bcrypt.hashpw(key_value.encode(), bcrypt.gensalt(rounds=12)).decode()
    api_key = AgentAPIKey(
        agent_registration_id=agent.id,
        name=f"Lab key — {agent.name}",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=_AGENT_SCOPES,
    )
    db.add(api_key)
    await db.flush()
    logger.info("lab_agent_api_key_seeded", agent_name=agent.name, key_prefix=key_prefix)


async def _seed_agents(
    db: AsyncSession, llm_integration: LLMIntegration
) -> dict[str, AgentRegistration]:
    """Seed 4 agents and their API keys. Returns a name→AgentRegistration map."""
    agents: dict[str, AgentRegistration] = {}

    for spec in _AGENT_SPECS:
        existing = await db.execute(
            select(AgentRegistration).where(AgentRegistration.name == spec["name"])
        )
        agent = existing.scalar_one_or_none()

        if agent is None:
            agent = AgentRegistration(
                name=spec["name"],
                description=spec.get("description"),
                execution_mode=spec["execution_mode"],
                agent_type=spec["agent_type"],
                role=spec.get("role"),
                status=spec["status"],
                adapter_type=spec["adapter_type"],
                llm_integration_id=llm_integration.id,
                system_prompt=spec.get("system_prompt"),
                methodology=spec.get("methodology"),
                capabilities=spec.get("capabilities"),
                trigger_on_severities=spec.get("trigger_on_severities", []),
                max_concurrent_alerts=spec.get("max_concurrent_alerts", 1),
                max_sub_agent_calls=spec.get("max_sub_agent_calls"),
                budget_monthly_cents=spec.get("budget_monthly_cents", 0),
            )
            db.add(agent)
            await db.flush()
            logger.info("lab_agent_seeded", name=agent.name)

        agents[str(spec["name"])] = agent

        key_value = _agent_key_value(str(spec["name"]))
        await _seed_agent_api_key(db, agent, key_value)

    # Wire up sub_agent_ids on lead-investigator
    lead = agents["lead-investigator"]
    specialist_uuids = [
        str(agents["threat-intel-analyst"].uuid),
        str(agents["identity-analyst"].uuid),
        str(agents["historical-context-analyst"].uuid),
    ]
    if lead.sub_agent_ids != specialist_uuids:
        lead.sub_agent_ids = specialist_uuids
        await db.flush()
        logger.info("lab_lead_investigator_sub_agents_wired", count=len(specialist_uuids))

    return agents


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

_ISSUE_SPECS = [
    {
        "title": "Block C2 IPs from ransomware beachhead alert",
        "category": "remediation",
        "status": "open",
        "priority": "high",
        "description": (
            "Three confirmed C2 IPs identified in alert a1b2c3. "
            "Firewall block rules need to be applied across all perimeter devices."
        ),
    },
    {
        "title": "Tune detection rule: excessive false positives on dev VPN",
        "category": "detection_tuning",
        "status": "in_progress",
        "priority": "medium",
        "description": (
            "Rule 'Suspicious Outbound Connection' fires 40+ times daily for the dev team "
            "VPN subnet 10.20.30.0/24. Add exclusion."
        ),
    },
    {
        "title": "Post-incident review: credential stuffing campaign",
        "category": "post_incident",
        "status": "open",
        "priority": "medium",
        "description": (
            "Write PIR for the credential stuffing campaign detected last week. "
            "Document TTPs, affected accounts, and timeline."
        ),
    },
    {
        "title": "Verify MFA enrollment for flagged accounts",
        "category": "investigation",
        "status": "open",
        "priority": "high",
        "description": (
            "Identity agent flagged 3 accounts with MFA bypass events. "
            "Confirm enrollment status and force re-registration."
        ),
    },
    {
        "title": "Update incident response runbook for ransomware",
        "category": "compliance",
        "status": "open",
        "priority": "low",
        "description": (
            "Ransomware IR runbook is 18 months old. Update with current tooling "
            "(CrowdStrike containment steps, Entra revocation)."
        ),
    },
    {
        "title": "Investigate lateral movement alerts on host WIN-PROD-07",
        "category": "investigation",
        "status": "in_progress",
        "priority": "high",
        "description": (
            "Three lateral movement alerts in 4 hours involving WIN-PROD-07 as source. "
            "Correlate with endpoint agent findings."
        ),
    },
    {
        "title": "Review and clean up stale agent registrations",
        "category": "maintenance",
        "status": "open",
        "priority": "low",
        "description": (
            "12 agent registrations in paused/terminated state from earlier testing. "
            "Review and remove unused entries."
        ),
    },
    {
        "title": "Evaluate GreyNoise enrichment provider integration",
        "category": "detection_tuning",
        "status": "open",
        "priority": "medium",
        "description": (
            "GreyNoise would add internet scanner context to IP enrichment. "
            "Evaluate API, rate limits, and add as enrichment provider."
        ),
    },
]


async def _next_identifier(db: AsyncSession) -> str:
    """Generate the next CAL-NNN identifier."""
    result = await db.execute(select(func.count()).select_from(AgentIssue))
    count = result.scalar() or 0
    return f"CAL-{count + 1:03d}"


async def _seed_issues(db: AsyncSession) -> None:
    """Seed 8 lab issues. Idempotent — checks by title before inserting."""
    created = 0

    for spec in _ISSUE_SPECS:
        existing = await db.execute(
            select(AgentIssue).where(AgentIssue.title == spec["title"])
        )
        if existing.scalar_one_or_none() is not None:
            continue

        identifier = await _next_identifier(db)
        issue = AgentIssue(
            identifier=identifier,
            title=spec["title"],
            category=spec["category"],
            status=spec["status"],
            priority=spec["priority"],
            description=spec.get("description"),
            created_by_operator="system",
        )
        db.add(issue)
        await db.flush()
        created += 1

    if created:
        logger.info("lab_issues_seeded", count=created)


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

_ROUTINE_SPECS = [
    {
        "name": "Daily High/Critical Alert Sweep",
        "description": (
            "Every morning at 7am, check for any unassigned High or Critical alerts "
            "that have been open for more than 2 hours"
        ),
        "status": "active",
        "concurrency_policy": "skip_if_active",
        "cron_expression": "0 7 * * *",
        "task_template": {
            "type": "alert_sweep",
            "filter": {"severities": ["High", "Critical"], "min_age_hours": 2},
        },
        "preferred_agent": "lead-investigator",
    },
    {
        "name": "Hourly Queue Depth Check",
        "description": (
            "If queue depth exceeds 10 unassigned enriched alerts, "
            "create a high-priority investigation issue"
        ),
        "status": "paused",
        "concurrency_policy": "skip_if_active",
        "cron_expression": "0 * * * *",
        "task_template": {
            "type": "queue_depth_check",
            "threshold": 10,
            "action": "create_issue",
        },
        "preferred_agent": "lead-investigator",
    },
    {
        "name": "Weekly Detection Rule Coverage Review",
        "description": (
            "Every Monday, generate a coverage report comparing active detection rules "
            "against MITRE ATT&CK techniques with no rule coverage"
        ),
        "status": "active",
        "concurrency_policy": "coalesce_if_active",
        "cron_expression": "0 9 * * 1",
        "task_template": {
            "type": "detection_coverage_report",
            "framework": "mitre_attack",
        },
        "preferred_agent": "lead-investigator",
    },
]


async def _seed_routines(
    db: AsyncSession, agents: dict[str, AgentRegistration]
) -> None:
    """Seed 3 lab routines with cron triggers. Idempotent — checks by name."""
    created = 0
    lead = agents["lead-investigator"]

    for spec in _ROUTINE_SPECS:
        existing = await db.execute(
            select(AgentRoutine).where(AgentRoutine.name == spec["name"])
        )
        if existing.scalar_one_or_none() is not None:
            continue

        routine = AgentRoutine(
            name=spec["name"],
            description=spec.get("description"),
            agent_registration_id=lead.id,
            status=spec["status"],
            concurrency_policy=spec["concurrency_policy"],
            task_template=spec["task_template"],
        )
        db.add(routine)
        await db.flush()

        trigger = RoutineTrigger(
            routine_id=routine.id,
            kind="cron",
            cron_expression=spec["cron_expression"],
            timezone="UTC",
            is_active=spec["status"] == "active",
        )
        db.add(trigger)
        await db.flush()
        created += 1

    if created:
        logger.info("lab_routines_seeded", count=created)


# ---------------------------------------------------------------------------
# KB Pages
# ---------------------------------------------------------------------------


def _slugify(folder: str, title: str) -> str:
    """Generate a URL-safe slug from folder + title."""
    raw = f"{folder}/{title}".lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-")


_KB_PAGE_SPECS = [
    {
        "title": "Ransomware Response Playbook",
        "folder": "/playbooks/ransomware",
        "inject_scope": {"global": False, "roles": ["investigation", "response"]},
        "body": """\
# Ransomware Response Playbook

## Immediate Actions (0–15 min)
1. Isolate affected host via CrowdStrike: `isolate_host` action
2. Revoke active sessions for affected user accounts
3. Preserve evidence: take memory dump before isolation if possible

## Investigation Steps
- Identify patient zero: check for first occurrence of suspicious process
- Map lateral movement: search alerts for same src_host in prior 48h
- Identify data staging: check for large outbound transfers, archive creation

## Indicators to Extract
- Ransom note filename (often README.txt, !!!HOW_TO_DECRYPT!!!)
- Encrypted file extension (e.g. .locked, .encrypted, .{random})
- C2 domain/IP (check DNS queries in SIEM)

## Escalation Criteria
Escalate to IR team if: >3 hosts affected, backup deletion confirmed,
or domain admin compromise suspected.
""",
    },
    {
        "title": "Credential Stuffing Response Playbook",
        "folder": "/playbooks/identity",
        "inject_scope": {"global": False, "roles": ["investigation"]},
        "body": """\
# Credential Stuffing Response Playbook

## Detection Signals
- Multiple failed logins from same IP across different accounts
- Successful login after spike in failures (credential reuse)
- Login from new country/ASN immediately after local session

## Investigation Steps
1. Identify the source IP range — enrich for reputation
2. Count affected accounts — search_alerts with actor_ip
3. Check for successful logins: filter by status=success in identity enrichment
4. Identify any accounts with MFA bypassed (check mfa_result field)

## Response Actions
- Block source IP range via Generic Webhook integration
- Force password reset for all accounts with successful login from flagged IP
- Notify security team if >50 accounts targeted
""",
    },
    {
        "title": "CrowdStrike Host Isolation Runbook",
        "folder": "/runbooks/endpoint",
        "inject_scope": {"global": False, "roles": ["response"]},
        "body": """\
# CrowdStrike Host Isolation Runbook

## When to Use
Use host isolation for confirmed malware execution, active C2 communication,
or lateral movement from a specific host.

## What It Does
Network isolation via CrowdStrike Falcon. Host retains connectivity to
Falcon cloud for continued sensor activity and command delivery.
Does NOT affect: management plane, Falcon sensor traffic.

## Rollback
`lift_containment` action in Calseta. Takes effect within 30 seconds.
Always verify the host is responding post-lift before marking resolved.

## Approval Requirements
Requires human approval (approval_mode = always) due to operational impact.
Include in `reason`: alert UUID, indicator that triggered, expected blast radius.
""",
    },
    {
        "title": "Entra ID Session Revocation Runbook",
        "folder": "/runbooks/identity",
        "inject_scope": {"global": False, "roles": ["response", "investigation"]},
        "body": """\
# Microsoft Entra ID Session Revocation Runbook

## When to Use
Suspicious login, impossible travel, MFA bypass, or confirmed account compromise.

## What It Does
Calls Microsoft Graph `revokeSignInSessions`. Terminates all active refresh tokens.
User must re-authenticate on all devices within ~1 hour.

## Steps
1. Confirm UPN from identity enrichment result
2. Execute `revoke_sessions` action in Calseta with `actor_account` indicator
3. Notify user via Slack (optional — use `send_alert` workflow)
4. Monitor for re-authentication from clean device

## Caveats
- Does NOT revoke existing access tokens (up to 1h lifetime)
- Does NOT block the account — use `disable_user` for higher severity
- Guest accounts require separate revocation
""",
    },
    {
        "title": "MITRE T1078 — Valid Accounts Detection Guidance",
        "folder": "/detection-guidance/initial-access",
        "inject_scope": {"global": True},
        "body": """\
# MITRE T1078 — Valid Accounts

## What to Look For
Adversaries use compromised credentials to gain initial access or maintain persistence.

## High-Signal Indicators
- Login from TOR/VPN exit node
- Login from country not in user's history
- Off-hours login + immediate high-privilege action
- Login from new device immediately after credential stuffing campaign
- Multiple simultaneous sessions from different IPs

## False Positive Sources
- VPN usage by remote workers (enrich source IP for VPN/corporate ASN)
- Travel (check if user has active travel request)
- Developers using multiple cloud environments

## Enrichment to Request
- Source IP: reputation, ASN, country, VPN detection
- Account: MFA status, last password change, recent risky sign-ins
""",
    },
    {
        "title": "Agent Memory Index",
        "folder": "/memory",
        "inject_scope": {"global": False},
        "body": """\
# Agent Memory Index

This folder contains persistent memory entries written by Calseta agents.
Subfolders are organized by agent ID: /memory/agents/{agent_id}/

Memory entries are automatically injected into agent prompts (Layer 6).
Entries older than the configured staleness TTL are prefixed with [STALE].

Do not edit these files manually unless correcting factual errors.
""",
    },
]


async def _seed_kb(db: AsyncSession) -> None:
    """Seed 6 KB pages. Idempotent — checks by (title, folder) before inserting."""
    created = 0

    for spec in _KB_PAGE_SPECS:
        existing = await db.execute(
            select(KnowledgeBasePage).where(
                KnowledgeBasePage.title == spec["title"],
                KnowledgeBasePage.folder == spec["folder"],
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        slug = _slugify(str(spec["folder"]), str(spec["title"]))
        # Ensure slug uniqueness if it already exists (shouldn't happen on clean seed)
        slug_check = await db.execute(
            select(KnowledgeBasePage).where(KnowledgeBasePage.slug == slug)
        )
        if slug_check.scalar_one_or_none() is not None:
            slug = f"{slug}-lab"

        page = KnowledgeBasePage(
            slug=slug,
            title=spec["title"],
            body=spec["body"],
            folder=spec["folder"],
            format="markdown",
            status="published",
            inject_scope=spec.get("inject_scope"),
            inject_priority=0,
            inject_pinned=False,
            created_by_operator="system",
        )
        db.add(page)
        await db.flush()
        created += 1

    if created:
        logger.info("lab_kb_pages_seeded", count=created)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def seed_control_plane(db: AsyncSession) -> None:
    """Seed control plane lab data. Idempotent."""
    llm_integration = await _seed_llm_integration(db)
    agents = await _seed_agents(db, llm_integration)
    await _seed_issues(db)
    await _seed_routines(db, agents)
    await _seed_kb(db)
    logger.info("lab_control_plane_seeded")
