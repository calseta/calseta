"""
Context targeting rule evaluation engine.

Evaluates which KB pages apply to a given alert based on:
  - inject_scope.global: True  → always included regardless of rules
  - targeting_rules            → evaluated per the match_any / match_all logic

A KB page participates in alert context if inject_scope is not None.
  - inject_scope = {"global": true} → always include
  - inject_scope set but not global → include when targeting_rules matches
    (if targeting_rules is None, match all alerts)
  - inject_scope = null → informational page, never in alert context

Rule operators:
  eq       — exact equality (string or numeric)
  in       — alert field value appears in the rule's list
  contains — rule value appears in the alert field list (for tags)
  gte      — alert field value >= rule value (numeric)
  lte      — alert field value <= rule value (numeric)

Field paths supported: source_name, severity, tags

Invalid field path or type mismatch evaluates as False (never raises).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert

# ---------------------------------------------------------------------------
# Alert field accessor
# ---------------------------------------------------------------------------

_FIELD_ACCESSORS: dict[str, str] = {
    "source_name": "source_name",
    "severity": "severity",
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
) -> list[Any]:
    """
    Return KB pages that apply to the given alert.

    Only pages with inject_scope set participate in alert context.

    Ordering:
      1. Global pages (inject_scope.global = true)
      2. Targeted pages whose targeting_rules match the alert's fields
         (pages with targeting_rules=None match all alerts)
    """
    from app.db.models.kb_page import KnowledgeBasePage  # noqa: F401
    from app.repositories.kb_repository import KBPageRepository

    repo = KBPageRepository(db)
    all_pages = await repo.list_all_for_alert_targeting()

    global_pages: list[Any] = []
    targeted_pages: list[Any] = []

    for page in all_pages:
        scope = page.inject_scope or {}
        if scope.get("global"):
            global_pages.append(page)
        elif evaluate_targeting_rules(alert, page.targeting_rules):
            targeted_pages.append(page)

    return global_pages + targeted_pages
