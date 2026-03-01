"""
Context targeting rule evaluation engine.

Evaluates which context documents apply to a given alert based on:
  - is_global: True  → always included regardless of rules
  - targeting_rules   → evaluated per the match_any / match_all logic

Rule operators:
  eq       — exact equality (string or numeric)
  in       — alert field value appears in the rule's list
  contains — rule value appears in the alert field list (for tags)
  gte      — alert field value >= rule value (numeric)
  lte      — alert field value <= rule value (numeric)

Field paths supported: source_name, severity, severity_id, tags

Invalid field path or type mismatch evaluates as False (never raises).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.context_document import ContextDocument
from app.repositories.context_document_repository import ContextDocumentRepository

# ---------------------------------------------------------------------------
# Alert field accessor
# ---------------------------------------------------------------------------

_FIELD_ACCESSORS: dict[str, str] = {
    "source_name": "source_name",
    "severity": "severity",
    "severity_id": "severity_id",
    "tags": "tags",
}


def _get_alert_field(alert: Alert, field: str) -> Any:
    """Return the alert attribute for a supported field name; None if unknown."""
    attr = _FIELD_ACCESSORS.get(field)
    if attr is None:
        return None
    return getattr(alert, attr, None)


# ---------------------------------------------------------------------------
# Single-rule evaluation
# ---------------------------------------------------------------------------


def _evaluate_rule(alert: Alert, rule: dict[str, Any]) -> bool:
    """
    Evaluate a single targeting rule against an alert.

    Returns False on any type mismatch or unknown field — never raises.
    """
    field = rule.get("field")
    op = rule.get("op")
    rule_value = rule.get("value")

    if not field or not op:
        return False

    alert_value = _get_alert_field(alert, field)
    if alert_value is None:
        return False

    try:
        if op == "eq":
            return str(alert_value) == str(rule_value)

        if op == "in":
            # alert field value is in the rule's list
            if not isinstance(rule_value, list):
                return False
            return str(alert_value) in [str(v) for v in rule_value]

        if op == "contains":
            # alert field is a list; rule value must be in it
            if not isinstance(alert_value, list):
                return False
            return str(rule_value) in [str(v) for v in alert_value]

        if op == "gte":
            return float(alert_value) >= float(rule_value)  # type: ignore[arg-type]

        if op == "lte":
            return float(alert_value) <= float(rule_value)  # type: ignore[arg-type]

    except (TypeError, ValueError):
        return False

    return False


# ---------------------------------------------------------------------------
# Targeting rules evaluation
# ---------------------------------------------------------------------------


def evaluate_targeting_rules(alert: Alert, rules: dict[str, Any] | None) -> bool:
    """
    Evaluate targeting_rules dict against an alert.

    - None rules → always matches (no restrictions)
    - match_any  → at least one rule must pass (OR)
    - match_all  → all rules must pass (AND)
    - Both present → both match_any AND match_all must pass
    """
    if rules is None:
        return True

    match_any = rules.get("match_any")
    match_all = rules.get("match_all")

    if not match_any and not match_all:
        # Empty rules structure — treated as no restriction
        return True

    any_ok = (
        not (match_any and isinstance(match_any, list))
        or any(_evaluate_rule(alert, r) for r in match_any)
    )
    all_ok = (
        not (match_all and isinstance(match_all, list))
        or all(_evaluate_rule(alert, r) for r in match_all)
    )
    return any_ok and all_ok


# ---------------------------------------------------------------------------
# Document applicability
# ---------------------------------------------------------------------------


async def get_applicable_documents(
    alert: Alert, db: AsyncSession
) -> list[ContextDocument]:
    """
    Return context documents that apply to the given alert.

    Ordering:
      1. Global documents (is_global=True), ordered by document_type asc
      2. Targeted documents that match the alert's fields, ordered by document_type asc

    Documents without targeting_rules (None) are included for all alerts.
    Documents with targeting_rules are included only if rules evaluate True.
    """
    repo = ContextDocumentRepository(db)
    all_docs = await repo.list_all_for_targeting()

    global_docs: list[ContextDocument] = []
    targeted_docs: list[ContextDocument] = []

    for doc in all_docs:
        if doc.is_global:
            global_docs.append(doc)
        elif evaluate_targeting_rules(alert, doc.targeting_rules):
            targeted_docs.append(doc)

    # Sort each group by document_type alphabetically
    global_docs.sort(key=lambda d: d.document_type)
    targeted_docs.sort(key=lambda d: d.document_type)

    return global_docs + targeted_docs
