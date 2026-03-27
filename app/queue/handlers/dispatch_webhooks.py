"""Handlers for agent webhook dispatch tasks."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.queue.handlers.payloads import (
    DispatchAgentWebhooksPayload,
    DispatchSingleAgentWebhookPayload,
)
from app.repositories.alert_repository import AlertRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.agent_dispatch import build_webhook_payload, dispatch_to_agent
from app.services.agent_trigger import get_matching_agents

logger = structlog.get_logger()


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
