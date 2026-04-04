"""CostService — records cost events and enforces agent budget limits."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.repositories.cost_event_repository import CostEventRepository
from app.schemas.cost_events import AgentBudgetStatus, CostEventCreate, CostSummaryResponse

logger = structlog.get_logger(__name__)


class CostService:
    """Records cost events and enforces per-agent monthly budget limits."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_cost(
        self,
        agent: AgentRegistration,
        data: CostEventCreate,
        db_alert_id: int | None = None,
        db_heartbeat_run_id: int | None = None,
    ) -> tuple[object, AgentBudgetStatus]:
        """Record a cost event and check the agent's monthly budget.

        Steps:
          1. Create cost_event row.
          2. Update agent.spent_monthly_cents.
          3. If budget_monthly_cents > 0 and spent >= budget → set status='paused',
             log a structlog warning (activity event written separately by the route handler
             or a future post-MVP enhancement).
          4. Return (cost_event, budget_status).

        budget_status.hard_stop_triggered=True if the monthly limit was just breached.
        """
        repo = CostEventRepository(self._db)

        # Resolve llm_integration_id — look it up from agent if not overridden
        llm_integration_id: int | None = agent.llm_integration_id

        cost_event = await repo.create(
            agent_id=agent.id,
            llm_integration_id=llm_integration_id,
            alert_id=db_alert_id,
            heartbeat_run_id=db_heartbeat_run_id,
            provider=data.provider,
            model=data.model,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            cost_cents=data.cost_cents,
            billing_type=data.billing_type,
        )

        # Update agent's running total
        agent.spent_monthly_cents = (agent.spent_monthly_cents or 0) + data.cost_cents
        await self._db.flush()

        # Evaluate hard stop
        hard_stop = (
            agent.budget_monthly_cents > 0
            and agent.spent_monthly_cents >= agent.budget_monthly_cents
        )

        if hard_stop and agent.status not in ("paused", "terminated"):
            agent.status = "paused"
            await self._db.flush()
            logger.warning(
                "agent_budget_hard_stop",
                agent_id=agent.id,
                budget_monthly_cents=agent.budget_monthly_cents,
                spent_monthly_cents=agent.spent_monthly_cents,
            )

        remaining = max(
            0, agent.budget_monthly_cents - agent.spent_monthly_cents
        ) if agent.budget_monthly_cents > 0 else 0

        budget_status = AgentBudgetStatus(
            monthly_cents=agent.budget_monthly_cents,
            spent_cents=agent.spent_monthly_cents,
            remaining_cents=remaining,
            hard_stop_triggered=hard_stop,
        )

        await self._db.commit()
        await self._db.refresh(cost_event)
        await self._db.refresh(agent)

        logger.info(
            "cost_event_recorded",
            agent_id=agent.id,
            cost_cents=data.cost_cents,
            billing_type=data.billing_type,
            spent_monthly_cents=agent.spent_monthly_cents,
            hard_stop=hard_stop,
        )

        return cost_event, budget_status

    async def reset_monthly_budget(self, agent: AgentRegistration) -> None:
        """Reset spent_monthly_cents=0 and budget_period_start=now()."""
        agent.spent_monthly_cents = 0
        agent.budget_period_start = datetime.now(UTC)
        await self._db.flush()
        await self._db.commit()
        await self._db.refresh(agent)

        logger.info("agent_budget_reset", agent_id=agent.id)

    async def get_summary_by_agent(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-agent cost summaries for the given time range."""
        from sqlalchemy import func, select

        from app.db.models.agent_registration import AgentRegistration as AgentModel
        from app.db.models.cost_event import CostEvent

        stmt = (
            select(
                CostEvent.agent_registration_id,
                AgentModel.name.label("agent_name"),
                func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
                func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
            )
            .join(AgentModel, CostEvent.agent_registration_id == AgentModel.id)
            .group_by(CostEvent.agent_registration_id, AgentModel.name)
        )

        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        return [
            {
                "agent_registration_id": row.agent_registration_id,
                "agent_name": row.agent_name,
                "total_cost_cents": int(row.total_cost_cents),
                "total_input_tokens": int(row.total_input_tokens),
                "total_output_tokens": int(row.total_output_tokens),
                "period_start": from_dt,
                "period_end": to_dt,
            }
            for row in result
        ]

    async def get_summary_by_alert(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-alert cost summaries for the given time range."""
        from sqlalchemy import func, select

        from app.db.models.alert import Alert
        from app.db.models.cost_event import CostEvent

        stmt = (
            select(
                CostEvent.alert_id,
                Alert.uuid.label("alert_uuid"),
                Alert.title.label("alert_title"),
                func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
                func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
            )
            .join(Alert, CostEvent.alert_id == Alert.id)
            .where(CostEvent.alert_id.is_not(None))
            .group_by(CostEvent.alert_id, Alert.uuid, Alert.title)
        )

        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        return [
            {
                "alert_id": row.alert_id,
                "alert_uuid": str(row.alert_uuid),
                "alert_title": row.alert_title,
                "total_cost_cents": int(row.total_cost_cents),
                "total_input_tokens": int(row.total_input_tokens),
                "total_output_tokens": int(row.total_output_tokens),
                "period_start": from_dt,
                "period_end": to_dt,
            }
            for row in result
        ]

    async def get_instance_summary(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> CostSummaryResponse:
        """Return instance-wide aggregated cost summary."""
        repo = CostEventRepository(self._db)
        raw = await repo.get_instance_summary(from_dt=from_dt, to_dt=to_dt)
        return CostSummaryResponse(
            total_cost_cents=int(raw["total_cost_cents"]),  # type: ignore[arg-type, call-overload]
            total_input_tokens=int(raw["total_input_tokens"]),  # type: ignore[arg-type, call-overload]
            total_output_tokens=int(raw["total_output_tokens"]),  # type: ignore[arg-type, call-overload]
            by_billing_type=raw["by_billing_type"],  # type: ignore[arg-type]
            period_start=raw["period_start"],  # type: ignore[arg-type]
            period_end=raw["period_end"],  # type: ignore[arg-type]
        )
