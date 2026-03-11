"""
MCP resources for detection rules.

Exposes detection rule data as MCP resources for AI agent consumption:
  - calseta://detection-rules         — Rule catalog with MITRE mappings and doc summaries
  - calseta://detection-rules/{uuid}  — Full rule with complete documentation
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server
from app.repositories.detection_rule_repository import DetectionRuleRepository


def _json_serial(obj: object) -> str:
    """JSON serializer for objects not handled by default json encoder."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _truncate_doc(documentation: str | None, max_length: int = 200) -> str | None:
    """Return a truncated documentation summary for list views."""
    if documentation is None:
        return None
    if len(documentation) <= max_length:
        return documentation
    return documentation[:max_length].rstrip() + "..."


@mcp_server.resource("calseta://detection-rules")
async def list_detection_rules(ctx: Context) -> str:
    """Detection rule catalog with MITRE mappings and documentation summaries."""
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        repo = DetectionRuleRepository(session)
        rules, _total = await repo.list(page=1, page_size=500)

        result = [
            {
                "uuid": str(rule.uuid),
                "name": rule.name,
                "source_name": rule.source_name,
                "severity": rule.severity,
                "is_active": rule.is_active,
                "mitre_tactics": rule.mitre_tactics,
                "mitre_techniques": rule.mitre_techniques,
                "mitre_subtechniques": rule.mitre_subtechniques,
                "data_sources": rule.data_sources,
                "documentation_summary": _truncate_doc(rule.documentation),
                "created_at": rule.created_at.isoformat(),
            }
            for rule in rules
        ]

        return json.dumps(
            {"detection_rules": result, "count": len(result)},
            default=_json_serial,
        )


@mcp_server.resource("calseta://detection-rules/{uuid}")
async def get_detection_rule(uuid: str, ctx: Context) -> str:
    """Full detection rule with complete documentation."""
    try:
        rule_uuid = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Invalid UUID: {uuid}") from None

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        repo = DetectionRuleRepository(session)
        rule = await repo.get_by_uuid(rule_uuid)
        if rule is None:
            raise ValueError(f"Detection rule not found: {uuid}")

        result = {
            "uuid": str(rule.uuid),
            "name": rule.name,
            "source_rule_id": rule.source_rule_id,
            "source_name": rule.source_name,
            "severity": rule.severity,
            "is_active": rule.is_active,
            "mitre_tactics": rule.mitre_tactics,
            "mitre_techniques": rule.mitre_techniques,
            "mitre_subtechniques": rule.mitre_subtechniques,
            "data_sources": rule.data_sources,
            "run_frequency": rule.run_frequency,
            "created_by": rule.created_by,
            "documentation": rule.documentation,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat(),
        }

        return json.dumps(result, default=_json_serial)
