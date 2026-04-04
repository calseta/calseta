"""CostEvent repository — all DB reads/writes for the cost_events table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.db.models.cost_event import CostEvent
from app.repositories.base import BaseRepository


class CostEventRepository(BaseRepository[CostEvent]):
    model = CostEvent

    async def create(
        self,
        agent_id: int,
        llm_integration_id: int | None,
        alert_id: int | None,
        heartbeat_run_id: int | None,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cents: int,
        billing_type: str = "api",
    ) -> CostEvent:
        """Append a new cost event row. Cost events are never updated after creation."""
        event = CostEvent(
            agent_registration_id=agent_id,
            llm_integration_id=llm_integration_id,
            alert_id=alert_id,
            heartbeat_run_id=heartbeat_run_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_cents=cost_cents,
            billing_type=billing_type,
        )
        self._db.add(event)
        await self._db.flush()
        await self._db.refresh(event)
        return event

    async def sum_for_agent_current_period(
        self,
        agent_id: int,
        period_start: datetime,
    ) -> int:
        """Return total cost_cents for an agent since period_start."""
        result = await self._db.execute(
            select(func.coalesce(func.sum(CostEvent.cost_cents), 0)).where(
                CostEvent.agent_registration_id == agent_id,
                CostEvent.occurred_at >= period_start,
            )
        )
        return int(result.scalar_one())

    async def get_summary_for_agent(
        self,
        agent_id: int,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> dict[str, object]:
        """Return aggregated cost summary for a single agent."""
        stmt = select(
            func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
            func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
        ).where(CostEvent.agent_registration_id == agent_id)

        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        row = result.one()

        # Breakdown by billing_type
        by_type = await self._get_by_billing_type(
            CostEvent.agent_registration_id == agent_id,
            from_dt=from_dt,
            to_dt=to_dt,
        )

        return {
            "total_cost_cents": int(row.total_cost_cents),
            "total_input_tokens": int(row.total_input_tokens),
            "total_output_tokens": int(row.total_output_tokens),
            "by_billing_type": by_type,
            "period_start": from_dt,
            "period_end": to_dt,
        }

    async def get_summary_for_alert(
        self,
        alert_id: int,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> dict[str, object]:
        """Return aggregated cost summary for a single alert."""
        stmt = select(
            func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
            func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
        ).where(CostEvent.alert_id == alert_id)

        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        row = result.one()

        by_type = await self._get_by_billing_type(
            CostEvent.alert_id == alert_id,
            from_dt=from_dt,
            to_dt=to_dt,
        )

        return {
            "total_cost_cents": int(row.total_cost_cents),
            "total_input_tokens": int(row.total_input_tokens),
            "total_output_tokens": int(row.total_output_tokens),
            "by_billing_type": by_type,
            "period_start": from_dt,
            "period_end": to_dt,
        }

    async def get_instance_summary(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> dict[str, object]:
        """Return instance-wide aggregated cost summary."""
        stmt = select(
            func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
            func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
        )

        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        row = result.one()

        from sqlalchemy.sql.elements import ColumnElement

        filters: list[ColumnElement[bool]] = []
        if from_dt is not None:
            filters.append(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            filters.append(CostEvent.occurred_at <= to_dt)

        by_type_stmt = (
            select(
                CostEvent.billing_type,
                func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total"),
            )
            .group_by(CostEvent.billing_type)
        )
        for f in filters:
            by_type_stmt = by_type_stmt.where(f)

        by_type_result = await self._db.execute(by_type_stmt)
        by_type: dict[str, int] = {r.billing_type: int(r.total) for r in by_type_result}

        return {
            "total_cost_cents": int(row.total_cost_cents),
            "total_input_tokens": int(row.total_input_tokens),
            "total_output_tokens": int(row.total_output_tokens),
            "by_billing_type": by_type,
            "period_start": from_dt,
            "period_end": to_dt,
        }

    async def _get_by_billing_type(
        self,
        *base_filters: object,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> dict[str, int]:
        """Helper: aggregate cost_cents by billing_type with optional time range."""
        stmt = (
            select(
                CostEvent.billing_type,
                func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total"),
            )
            .group_by(CostEvent.billing_type)
        )
        for f in base_filters:
            stmt = stmt.where(f)  # type: ignore[arg-type]
        if from_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(CostEvent.occurred_at <= to_dt)

        result = await self._db.execute(stmt)
        return {row.billing_type: int(row.total) for row in result}
