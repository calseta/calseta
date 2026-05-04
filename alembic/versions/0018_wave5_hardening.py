"""Wave 5 hardening — combined schema + data migration.

Consolidates three Wave 5 chunks that each landed an independent migration in
their own worktree. Merged into one revision so the alembic chain stays
linear:

* **S17** — drop UNIQUE constraint on ``api_keys.key_prefix`` and replace it
  with a non-unique B-tree index. Prefix collisions are legitimate (lab keys
  share ``cak_lab_``); the auth backend already iterates candidates and
  bcrypt-checks each. The unique constraint would block new key creation on
  collision.
* **S14** — add ``skills.source`` (``'manual'`` | ``'bundled'``) and
  ``skills.content_sha256`` columns. The bundled-skill loader only reconciles
  rows where ``source = 'bundled'`` so operator-edited skills are never
  clobbered. Backfills known bundled slugs.
* **S15** — rewrite every ``alerts.agent_findings`` JSONB row to the
  canonical ``FindingResponse`` shape (``id, agent_name, summary, confidence
  enum, recommended_action, evidence, posted_at``). Idempotent — already-
  canonical rows are skipped. Reversible (best-effort) via the originals
  preserved under ``evidence.*``.

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

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# S14 — bundled-skill backfill
# ---------------------------------------------------------------------------

# Slugs of bundled skills shipped in the repo at the time of this migration.
# Used only for backfill — the runtime loader re-discovers them at startup.
_BUNDLED_SLUGS_AT_MIGRATION_TIME = ("calseta",)


# ---------------------------------------------------------------------------
# S15 — agent_findings canonicalization helpers
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
    """Best-effort inverse for downgrade — pulls originals out of evidence.*."""
    ev = f.get("evidence") or {}
    raw_confidence = ev.get("confidence_raw")
    if raw_confidence is None:
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


def _agent_name_lookup(conn: Any) -> dict[int, str]:
    rows = conn.execute(
        sa.text("SELECT id, name FROM agent_registrations")
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def _rewrite_agent_findings(direction: str) -> None:
    """direction == 'up' canonicalizes; 'down' restores legacy shape."""
    conn = op.get_bind()
    name_by_agent_id = _agent_name_lookup(conn) if direction == "up" else {}

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
            canonical = _is_canonical(f)
            if direction == "up":
                if canonical:
                    new_list.append(f)
                    continue
                legacy_agent_id = f.get("agent_id")
                fallback_name = (
                    name_by_agent_id.get(int(legacy_agent_id))
                    if isinstance(legacy_agent_id, int)
                    else None
                ) or "unknown-agent"
                new_list.append(
                    _legacy_to_canonical(f, fallback_agent_name=fallback_name),
                )
                rewrote = True
            else:  # down
                if canonical:
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


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # --- S17: api key prefix uniqueness ---
    op.drop_constraint("api_keys_key_prefix_key", "api_keys", type_="unique")
    op.create_index(
        "idx_api_keys_key_prefix",
        "api_keys",
        ["key_prefix"],
    )

    # --- S14: skills.source + content_sha256 + backfill ---
    op.add_column(
        "skills",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )
    op.add_column(
        "skills",
        sa.Column("content_sha256", sa.Text(), nullable=True),
    )
    if _BUNDLED_SLUGS_AT_MIGRATION_TIME:
        op.execute(
            sa.text(
                "UPDATE skills SET source = 'bundled' "
                "WHERE slug = ANY(:slugs)",
            ).bindparams(
                sa.bindparam(
                    "slugs",
                    list(_BUNDLED_SLUGS_AT_MIGRATION_TIME),
                    type_=sa.ARRAY(sa.Text()),
                ),
            ),
        )

    # --- S15: agent_findings canonicalization (data fix) ---
    _rewrite_agent_findings(direction="up")


def downgrade() -> None:
    # Reverse order of upgrade.

    # --- S15 inverse ---
    _rewrite_agent_findings(direction="down")

    # --- S14 inverse ---
    op.drop_column("skills", "content_sha256")
    op.drop_column("skills", "source")

    # --- S17 inverse ---
    op.drop_index("idx_api_keys_key_prefix", table_name="api_keys")
    op.create_unique_constraint(
        "api_keys_key_prefix_key", "api_keys", ["key_prefix"],
    )
