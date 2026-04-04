"""Handlers for agent webhook dispatch tasks."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.queue.handlers.payloads import (
    DispatchAgentWebhooksPayload,
    DispatchSingleAgentWebhookPayload,
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.alert_repository import AlertRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.agent_dispatch import build_webhook_payload, dispatch_to_agent
from app.services.context_targeting import evaluate_targeting_rules

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Agent trigger evaluation
#
# After enrichment completes, determines which registered agents should receive
# the alert as a webhook payload.
#
# Evaluation order (all three layers must pass):
#   1. status != 'active' → skip (agents must be active)
#   2. trigger_on_sources (TEXT[]) → if non-empty, alert.source_name must be in list
#   3. trigger_on_severities (TEXT[]) → if non-empty, alert.severity must be in list
#   4. trigger_filter (JSONB) → evaluated using evaluate_targeting_rules()
#
# Empty list = match all (no filter applied for that dimension).
# ---------------------------------------------------------------------------


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


class DispatchWebhooksHandler:
    """Evaluate trigger criteria and dispatch alert to all matching agents.

    Enqueued after enrichment completes for each alert.
    Idempotent: re-dispatching sends the webhook again (operators can
    use POST /v1/alerts/{uuid}/trigger-agents to re-trigger manually).
    """

    async def execute(
        self, payload: DispatchAgentWebhooksPayload, session: AsyncSession
    ) -> None:
        alert_id = payload.alert_id
        alert_repo = AlertRepository(session)
        alert = await alert_repo.get_by_id(alert_id)
        if alert is None:
            return  # Alert deleted before task ran

        agents = await get_matching_agents(alert, session)
        if not agents:
            return

        webhook_payload = await build_webhook_payload(alert_id, session)

        for agent in agents:
            try:
                result = await dispatch_to_agent(
                    agent, alert_id, webhook_payload, session
                )

                # Write activity event for the dispatch
                try:
                    activity_svc = ActivityEventService(session)
                    await activity_svc.write(
                        ActivityEventType.AGENT_WEBHOOK_DISPATCHED,
                        actor_type="system",
                        actor_key_prefix=None,
                        alert_id=alert_id,
                        references={
                            "agent_name": agent.name,
                            "agent_uuid": str(agent.uuid),
                            "status": result.get("status", "unknown"),
                            "status_code": result.get("status_code"),
                            "attempt_count": result.get("attempt_count", 0),
                        },
                    )
                except Exception:
                    logger.exception(
                        "agent_dispatch_activity_event_failed",
                        agent_uuid=str(agent.uuid),
                        alert_id=alert_id,
                    )

                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "agent_dispatch_failed",
                    agent_uuid=str(agent.uuid),
                    alert_id=alert_id,
                )


class DispatchSingleWebhookHandler:
    """Dispatch an alert to a single specific agent (bypasses trigger matching).

    Enqueued by POST /v1/alerts/{uuid}/dispatch-agent for manual agent runs.
    """

    async def execute(
        self, payload: DispatchSingleAgentWebhookPayload, session: AsyncSession
    ) -> None:
        alert_id = payload.alert_id
        agent_id = payload.agent_id

        agent_result = await session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent is None:
            logger.warning("dispatch_single_agent_not_found", agent_id=agent_id)
            return

        webhook_payload = await build_webhook_payload(alert_id, session)
        if not webhook_payload:
            logger.warning("dispatch_single_alert_not_found", alert_id=alert_id)
            return

        result = await dispatch_to_agent(agent, alert_id, webhook_payload, session)

        # Write activity event for the dispatch
        try:
            activity_svc = ActivityEventService(session)
            await activity_svc.write(
                ActivityEventType.AGENT_WEBHOOK_DISPATCHED,
                actor_type="system",
                actor_key_prefix=None,
                alert_id=alert_id,
                references={
                    "agent_name": agent.name,
                    "agent_uuid": str(agent.uuid),
                    "status": result.get("status", "unknown"),
                    "status_code": result.get("status_code"),
                    "attempt_count": result.get("attempt_count", 0),
                },
            )
        except Exception:
            logger.exception(
                "agent_dispatch_activity_event_failed",
                agent_id=agent_id,
                alert_id=alert_id,
            )
