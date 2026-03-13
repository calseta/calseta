"""
Agent trigger evaluation engine.

After enrichment completes, determines which registered agents should receive
the alert as a webhook payload.

Evaluation order (all three layers must pass):
  1. is_active=False → skip (agents must be active)
  2. trigger_on_sources (TEXT[]) → if non-empty, alert.source_name must be in list
  3. trigger_on_severities (TEXT[]) → if non-empty, alert.severity must be in list
  4. trigger_filter (JSONB) → evaluated using evaluate_targeting_rules()

Empty list = match all (no filter applied for that dimension).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.repositories.agent_repository import AgentRepository
from app.services.context_targeting import evaluate_targeting_rules


async def get_matching_agents(
    alert: Alert,
    db: AsyncSession,
) -> list[AgentRegistration]:
    """
    Return active registered agents whose trigger criteria match the given alert.

    Called after enrichment completes. Does not modify any state.
    """
    repo = AgentRepository(db)
    active_agents = await repo.list_active()

    matches: list[AgentRegistration] = []
    for agent in active_agents:
        if not _passes_source_filter(agent, alert):
            continue
        if not _passes_severity_filter(agent, alert):
            continue
        if not _passes_jsonb_filter(agent, alert):
            continue
        matches.append(agent)

    return matches


def _passes_source_filter(agent: AgentRegistration, alert: Alert) -> bool:
    """Empty list = match all sources."""
    if not agent.trigger_on_sources:
        return True
    return alert.source_name in agent.trigger_on_sources


def _passes_severity_filter(agent: AgentRegistration, alert: Alert) -> bool:
    """Empty list = match all severities."""
    if not agent.trigger_on_severities:
        return True
    return alert.severity in agent.trigger_on_severities


def _passes_jsonb_filter(agent: AgentRegistration, alert: Alert) -> bool:
    """None trigger_filter = match all alerts."""
    return evaluate_targeting_rules(alert, agent.trigger_filter)
