"""Built-in tool seeder — auto-registers Calseta's built-in tools at startup.

Idempotent: uses upsert so re-running on a live DB is a safe no-op.
Only mutable metadata fields (display_name, description, tier, etc.) are
updated on conflict — is_active is never reset by this seeder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

BUILTIN_TOOLS: list[dict[str, object]] = [
    {
        "id": "get_alert",
        "display_name": "Get Alert",
        "description": (
            "Retrieve a security alert by UUID including enrichment results, "
            "indicators, and detection rule. Use when you need full details "
            "about a specific alert."
        ),
        "tier": "safe",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "alert_uuid": {"type": "string", "description": "UUID of the alert"},
            },
            "required": ["alert_uuid"],
        },
        "handler_ref": "calseta:get_alert",
    },
    {
        "id": "search_alerts",
        "display_name": "Search Alerts",
        "description": (
            "Search security alerts by status, severity, source, or keyword. "
            "Returns a list of matching alerts with key fields. Use for finding "
            "related alerts or building investigation context."
        ),
        "tier": "safe",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["Open", "Triaging", "Escalated", "Closed"],
                },
                "severity": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "maximum": 100},
            },
        },
        "handler_ref": "calseta:search_alerts",
    },
    {
        "id": "get_enrichment",
        "display_name": "Get Enrichment",
        "description": (
            "Get enrichment results for an indicator (IP, domain, hash, email, URL). "
            "Returns threat intelligence from all configured providers."
        ),
        "tier": "safe",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_type": {
                    "type": "string",
                    "enum": [
                        "ip",
                        "domain",
                        "hash_md5",
                        "hash_sha1",
                        "hash_sha256",
                        "url",
                        "email",
                        "account",
                    ],
                },
                "value": {"type": "string"},
            },
            "required": ["indicator_type", "value"],
        },
        "handler_ref": "calseta:get_enrichment",
    },
    {
        "id": "post_finding",
        "display_name": "Post Finding",
        "description": (
            "Record an investigation finding on a security alert. Include confidence "
            "score (0.0-1.0), classification, and detailed reasoning. Use after "
            "completing analysis."
        ),
        "tier": "managed",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "alert_uuid": {"type": "string"},
                "classification": {
                    "type": "string",
                    "enum": [
                        "true_positive",
                        "false_positive",
                        "benign",
                        "inconclusive",
                    ],
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "reasoning": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["alert_uuid", "classification", "confidence", "reasoning"],
        },
        "handler_ref": "calseta:post_finding",
    },
    {
        "id": "update_alert_status",
        "display_name": "Update Alert Status",
        "description": (
            "Update the lifecycle status of a security alert. Use to transition "
            "alerts from Open → Triaging → Escalated or → Closed as investigation "
            "progresses."
        ),
        "tier": "managed",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "alert_uuid": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["Open", "Triaging", "Escalated", "Closed"],
                },
                "reason": {"type": "string"},
            },
            "required": ["alert_uuid", "status"],
        },
        "handler_ref": "calseta:update_alert_status",
    },
    {
        "id": "get_detection_rule",
        "display_name": "Get Detection Rule",
        "description": (
            "Get details about a detection rule including MITRE techniques, data "
            "sources, and documentation. Helps understand what triggered the alert."
        ),
        "tier": "safe",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_uuid": {"type": "string"},
            },
            "required": ["rule_uuid"],
        },
        "handler_ref": "calseta:get_detection_rule",
    },
    {
        "id": "execute_workflow",
        "display_name": "Execute Workflow",
        "description": (
            "Execute a Calseta workflow (HTTP automation script). Requires human "
            "approval for high-risk workflows. Check workflow.approval_mode before "
            "proposing."
        ),
        "tier": "requires_approval",
        "category": "calseta_api",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_uuid": {"type": "string"},
                "indicator_value": {"type": "string"},
                "indicator_type": {"type": "string"},
                "alert_uuid": {"type": "string"},
            },
            "required": ["workflow_uuid"],
        },
        "handler_ref": "calseta:execute_workflow",
    },
]


async def seed_builtin_tools(db: AsyncSession) -> None:
    """Upsert all built-in tools. Called at startup. Safe to re-run."""
    from app.repositories.agent_tool_repository import AgentToolRepository
    from app.schemas.agent_tools import AgentToolCreate

    repo = AgentToolRepository(db)
    for tool_data in BUILTIN_TOOLS:
        await repo.upsert(AgentToolCreate(**tool_data))  # type: ignore[arg-type]

    logger.info("builtin_tools_seeded", count=len(BUILTIN_TOOLS))
