"""Canonicalize alerts.agent_findings JSONB rows to the FindingResponse shape.

Wave 5 / S15. One-shot data fix that rewrites every legacy finding object
in alerts.agent_findings to the canonical {id, agent_name, summary,
confidence (enum), recommended_action, evidence, posted_at} shape.

Idempotent: rows whose finding objects already carry the canonical keys
(agent_name AND summary AND posted_at) are skipped.

Reversible (best-effort): downgrade restores the legacy
{classification, confidence (numeric), reasoning, findings, recorded_at,
agent_id} shape for findings whose evidence still carries the originals.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Helpers (kept inline so the migration is self-contained)
# ---------------------------------------------------------------------------


def _confidence_numeric_to_enum(raw: Any) -> str | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value >= 0.75:
        return "high"
    if value >= 0.4:
        return "medium"
    return "low"


def _is_canonical(f: dict[str, Any]) -> bool:
    return (
        isinstance(f.get("agent_name"), str)
        and isinstance(f.get("summary"), str)
        and isinstance(f.get("posted_at"), str)
    )


def _legacy_to_canonical(
    f: dict[str, Any],
    fallback_agent_name: str = "unknown-agent",
) -> dict[str, Any]:
    """Translate a legacy finding object into the canonical shape."""
    raw_reasoning = f.get("reasoning")
    summary = (raw_reasoning or "").strip() or "(no reasoning provided)"
    raw_confidence = f.get("confidence")
    classification = f.get("classification")
    extras = f.get("findings") or []
    posted_at = f.get("recorded_at") or datetime.now(UTC).isoformat()

    evidence: dict[str, Any] = {}
    if classification is not None:
        evidence["classification"] = classification
    if extras:
        evidence["findings"] = extras
    if raw_confidence is not None:
        evidence["confidence_raw"] = raw_confidence
    if raw_reasoning is not None and raw_reasoning != summary:
        evidence["reasoning"] = raw_reasoning
    if "agent_id" in f and f["agent_id"] is not None:
        evidence["agent_id"] = f["agent_id"]

    return {
        "id": f.get("id") or str(uuid4()),
        "agent_name": f.get("agent_name") or fallback_agent_name,
        "summary": summary,
        "confidence": _confidence_numeric_to_enum(raw_confidence),
        "recommended_action": f.get("recommended_action"),
        "evidence": evidence or None,
        "posted_at": posted_at,
    }


def _canonical_to_legacy(f: dict[str, Any]) -> dict[str, Any]:
    """Best-effort inverse for downgrade.

    Pulls originals out of evidence.* when available; otherwise leaves
    minimal placeholders so the row is still readable.
    """
    ev = f.get("evidence") or {}
    raw_confidence = ev.get("confidence_raw")
    if raw_confidence is None:
        # Map enum back to a representative midpoint
        enum_to_num = {"high": 0.9, "medium": 0.6, "low": 0.2}
        raw_confidence = enum_to_num.get(f.get("confidence") or "")
    return {
        "classification": ev.get("classification"),
        "confidence": raw_confidence,
        "reasoning": ev.get("reasoning") or f.get("summary"),
        "findings": ev.get("findings") or [],
        "recorded_at": f.get("posted_at"),
        "agent_id": ev.get("agent_id"),
    }


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------


def _agent_name_lookup(conn: Any) -> dict[int, str]:
    """Build {agent_registration.id: name} map for filling missing agent_name."""
    rows = conn.execute(
        # Plain SQL keeps the migration ORM-free.
        # Using sa.text avoids importing the ORM model at migration time.
        __import__("sqlalchemy").text("SELECT id, name FROM agent_registrations"),
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def upgrade() -> None:
    import sqlalchemy as sa

    conn = op.get_bind()
    name_by_agent_id = _agent_name_lookup(conn)

    rows = conn.execute(
        sa.text(
            "SELECT id, agent_findings FROM alerts "
            "WHERE agent_findings IS NOT NULL "
            "AND jsonb_array_length(agent_findings) > 0",
        ),
    ).fetchall()

    for alert_id, agent_findings in rows:
        # Some drivers return the JSONB as a parsed list; others as a JSON string.
        if isinstance(agent_findings, str):
            findings_list = json.loads(agent_findings)
        else:
            findings_list = agent_findings

        if not isinstance(findings_list, list):
            continue

        rewrote = False
        new_list: list[dict[str, Any]] = []
        for f in findings_list:
            if not isinstance(f, dict):
                # Defensive: keep as-is, can't rewrite a non-object
                new_list.append(f)
                continue
            if _is_canonical(f):
                new_list.append(f)
                continue
            legacy_agent_id = f.get("agent_id")
            fallback_name = (
                name_by_agent_id.get(int(legacy_agent_id))
                if isinstance(legacy_agent_id, int)
                else None
            ) or "unknown-agent"
            new_list.append(_legacy_to_canonical(f, fallback_agent_name=fallback_name))
            rewrote = True

        if rewrote:
            conn.execute(
                sa.text(
                    "UPDATE alerts SET agent_findings = CAST(:val AS jsonb) "
                    "WHERE id = :id",
                ),
                {"val": json.dumps(new_list), "id": alert_id},
            )


def downgrade() -> None:
    import sqlalchemy as sa

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, agent_findings FROM alerts "
            "WHERE agent_findings IS NOT NULL "
            "AND jsonb_array_length(agent_findings) > 0",
        ),
    ).fetchall()

    for alert_id, agent_findings in rows:
        if isinstance(agent_findings, str):
            findings_list = json.loads(agent_findings)
        else:
            findings_list = agent_findings

        if not isinstance(findings_list, list):
            continue

        new_list: list[dict[str, Any]] = []
        rewrote = False
        for f in findings_list:
            if not isinstance(f, dict):
                new_list.append(f)
                continue
            if _is_canonical(f):
                new_list.append(_canonical_to_legacy(f))
                rewrote = True
            else:
                new_list.append(f)

        if rewrote:
            conn.execute(
                sa.text(
                    "UPDATE alerts SET agent_findings = CAST(:val AS jsonb) "
                    "WHERE id = :id",
                ),
                {"val": json.dumps(new_list), "id": alert_id},
            )
