"""
MCP tool for searching detection rules.

Tool:
  - search_detection_rules — Search rules by MITRE mapping or name
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

import structlog
from mcp.server.fastmcp import Context
from sqlalchemy import case, func, literal, or_, select

from app.db.models.detection_rule import DetectionRule
from app.db.session import AsyncSessionLocal
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server

# CASE expression for severity ordering in MCP queries
_MCP_SEVERITY_ORDER = case(
    (DetectionRule.severity == "Critical", 5),
    (DetectionRule.severity == "High", 4),
    (DetectionRule.severity == "Medium", 3),
    (DetectionRule.severity == "Low", 2),
    (DetectionRule.severity == "Informational", 1),
    (DetectionRule.severity == "Pending", 0),
    else_=0,
)

_MCP_SORT_COLUMNS: dict[str, str] = {
    "name": "name",
    "source_name": "source_name",
    "created_at": "created_at",
}

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def search_detection_rules(
    ctx: Context,
    name: str | None = None,
    mitre_tactic: str | None = None,
    mitre_technique: str | None = None,
    source_name: str | None = None,
    is_active: bool | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Search detection rules by name, MITRE ATT&CK mapping, or source.

    At least one filter should be provided for meaningful results.

    Args:
        name: Substring search against rule name (case-insensitive).
        mitre_tactic: Filter by MITRE ATT&CK tactic (e.g. "Initial Access").
        mitre_technique: Filter by MITRE technique ID (e.g. "T1566").
        source_name: Filter by alert source (e.g. "sentinel", "elastic").
        is_active: Filter by active status (true/false).
        sort_by: Sort field. Valid values: "name", "source_name", "severity", "created_at".
        sort_order: Sort direction. Valid values: "asc", "desc".
        page: Page number (1-indexed, default 1).
        page_size: Results per page (default 20, max 100).

    Returns:
        JSON with matching detection rules and pagination metadata.
    """
    page_size = min(page_size, 100)

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        stmt = select(DetectionRule)
        count_stmt = select(func.count()).select_from(DetectionRule)

        if name:
            name_filter = DetectionRule.name.ilike(f"%{name}%")
            stmt = stmt.where(name_filter)
            count_stmt = count_stmt.where(name_filter)

        if mitre_tactic:
            tactic_filter = DetectionRule.mitre_tactics.any(literal(mitre_tactic))
            stmt = stmt.where(tactic_filter)
            count_stmt = count_stmt.where(tactic_filter)

        if mitre_technique:
            technique_filter = or_(
                DetectionRule.mitre_techniques.any(literal(mitre_technique)),
                DetectionRule.mitre_subtechniques.any(literal(mitre_technique)),
            )
            stmt = stmt.where(technique_filter)
            count_stmt = count_stmt.where(technique_filter)

        if source_name:
            # Support comma-separated multi-value
            vals = [s.strip() for s in source_name.split(",") if s.strip()]
            if len(vals) == 1:
                stmt = stmt.where(DetectionRule.source_name == vals[0])
                count_stmt = count_stmt.where(DetectionRule.source_name == vals[0])
            else:
                stmt = stmt.where(DetectionRule.source_name.in_(vals))
                count_stmt = count_stmt.where(DetectionRule.source_name.in_(vals))

        if is_active is not None:
            stmt = stmt.where(DetectionRule.is_active == is_active)
            count_stmt = count_stmt.where(DetectionRule.is_active == is_active)

        total_result = await session.execute(count_stmt)
        total: int = total_result.scalar_one()

        # Dynamic sort
        order_clause = None
        if sort_by and sort_by in _MCP_SORT_COLUMNS:
            col = getattr(DetectionRule, _MCP_SORT_COLUMNS[sort_by])
            order_clause = col.asc() if sort_order == "asc" else col.desc()
        elif sort_by == "severity":
            order_clause = (
                _MCP_SEVERITY_ORDER.asc() if sort_order == "asc" else _MCP_SEVERITY_ORDER.desc()
            )

        if order_clause is None:
            order_clause = DetectionRule.created_at.desc()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(order_clause).offset(offset).limit(page_size)
        result = await session.execute(stmt)
        rules = list(result.scalars().all())

        data = [
            {
                "uuid": str(r.uuid),
                "name": r.name,
                "source_name": r.source_name,
                "severity": r.severity,
                "is_active": r.is_active,
                "mitre_tactics": r.mitre_tactics,
                "mitre_techniques": r.mitre_techniques,
                "mitre_subtechniques": r.mitre_subtechniques,
                "documentation": r.documentation[:200] + "..."
                if r.documentation and len(r.documentation) > 200
                else r.documentation,
                "created_at": r.created_at.isoformat(),
            }
            for r in rules
        ]

        return json.dumps({
            "detection_rules": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        }, default=_json_serial)
