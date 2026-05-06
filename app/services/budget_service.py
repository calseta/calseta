"""BudgetService — authoritative budget enforcement against ``cost_events``.

Replaces the previous in-process ``total_cost_cents`` counter and the
``agent.spent_monthly_cents`` stored column. Both were racy: concurrent runs
of the same agent kept private counters, so per-alert and monthly limits
could be exceeded N× by N concurrent runs.

Design (locked 2026-05-05):

* **Per-alert spend** = ``SELECT SUM(cost_cents) FROM cost_events WHERE
  agent_registration_id = $1 AND alert_id = $2``.
* **Monthly spend** = same SUM keyed on ``occurred_at >= date_trunc('month',
  now() AT TIME ZONE 'UTC')``.
* **Locking**: a Postgres advisory transaction lock keyed on
  ``hashtext(agent_id::text || ':' || alert_id::text)``. Auto-released at
  transaction end. Used by ``acquire_alert_lock`` so two heartbeats racing
  the same alert serialize their budget checks.
* **Subscription billing**: rows with ``billing_type='subscription'``
  (Claude Code) carry ``cost_cents=0`` and bypass the per-alert / monthly
  budget gate entirely (nothing to enforce against).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select, text

from app.db.models.cost_event import CostEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.agent_registration import AgentRegistration

logger = structlog.get_logger(__name__)


class BudgetLockUnavailable(RuntimeError):
    """Raised when a non-blocking advisory lock acquisition fails."""


@dataclass(slots=True)
class BudgetCheckResult:
    """Outcome of a budget check.

    ``allowed`` is True when the agent is under its limit (or the limit is
    unlimited / not set). ``reason`` is None when allowed; one of
    ``"per_alert_exceeded"`` / ``"monthly_exceeded"`` otherwise.
    """

    allowed: bool
    reason: str | None
    spent_cents: int
    limit_cents: int
    scope: str  # "alert" | "monthly"


class BudgetService:
    """Reads authoritative spend state from ``cost_events``.

    Holds no in-process counters. Every check is a fresh SUM query, so
    concurrent runs of the same agent observe the same total.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    async def acquire_alert_lock(self, agent_id: int, alert_id: int) -> None:
        """Try to take a Postgres advisory transaction lock for ``(agent, alert)``.

        Uses ``pg_try_advisory_xact_lock`` (non-blocking). The lock is
        automatically released at transaction end (commit or rollback). When
        the lock is unavailable (another concurrent run owns it for the same
        pair), raises ``BudgetLockUnavailable`` so the caller can release the
        assignment and back off.
        """
        stmt = text(
            "SELECT pg_try_advisory_xact_lock("
            "hashtext(:key)::bigint"
            ") AS got"
        )
        key = f"{agent_id}:{alert_id}"
        row = (await self._db.execute(stmt, {"key": key})).one()
        if not bool(row.got):
            raise BudgetLockUnavailable(
                f"Advisory lock unavailable for agent={agent_id} alert={alert_id}"
            )

    # ------------------------------------------------------------------
    # Spend queries
    # ------------------------------------------------------------------

    async def _sum_for_alert(self, agent_id: int, alert_id: int) -> int:
        stmt = select(func.coalesce(func.sum(CostEvent.cost_cents), 0)).where(
            CostEvent.agent_registration_id == agent_id,
            CostEvent.alert_id == alert_id,
        )
        return int((await self._db.execute(stmt)).scalar_one())

    async def _sum_for_month(
        self, agent_id: int, ref_dt: datetime | None = None,
    ) -> int:
        # Month boundary is the start of the current UTC month for ``ref_dt``.
        ref = ref_dt or datetime.now(UTC)
        month_start = datetime(ref.year, ref.month, 1, tzinfo=UTC)
        stmt = select(func.coalesce(func.sum(CostEvent.cost_cents), 0)).where(
            CostEvent.agent_registration_id == agent_id,
            CostEvent.occurred_at >= month_start,
        )
        return int((await self._db.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Public checks
    # ------------------------------------------------------------------

    async def check_per_alert(
        self,
        agent: AgentRegistration,
        alert_id: int | None,
    ) -> BudgetCheckResult:
        """Check whether the agent is under its per-alert cap for ``alert_id``.

        ``agent.max_cost_per_alert_cents == 0`` means unlimited — always
        allowed. ``alert_id is None`` (e.g. a one-off invocation not tied to
        an alert) is treated as unlimited too.
        """
        limit = int(agent.max_cost_per_alert_cents or 0)
        if limit <= 0 or alert_id is None:
            return BudgetCheckResult(
                allowed=True, reason=None, spent_cents=0,
                limit_cents=limit, scope="alert",
            )
        spent = await self._sum_for_alert(agent.id, alert_id)
        if spent >= limit:
            return BudgetCheckResult(
                allowed=False, reason="per_alert_exceeded",
                spent_cents=spent, limit_cents=limit, scope="alert",
            )
        return BudgetCheckResult(
            allowed=True, reason=None, spent_cents=spent,
            limit_cents=limit, scope="alert",
        )

    async def check_monthly(
        self,
        agent: AgentRegistration,
        ref_dt: datetime | None = None,
    ) -> BudgetCheckResult:
        """Check whether the agent is under its monthly budget.

        ``agent.budget_monthly_cents == 0`` means unlimited. The window is
        ``[start_of_current_utc_month, now]``.
        """
        limit = int(agent.budget_monthly_cents or 0)
        if limit <= 0:
            spent = await self._sum_for_month(agent.id, ref_dt)
            return BudgetCheckResult(
                allowed=True, reason=None, spent_cents=spent,
                limit_cents=limit, scope="monthly",
            )
        spent = await self._sum_for_month(agent.id, ref_dt)
        if spent >= limit:
            return BudgetCheckResult(
                allowed=False, reason="monthly_exceeded",
                spent_cents=spent, limit_cents=limit, scope="monthly",
            )
        return BudgetCheckResult(
            allowed=True, reason=None, spent_cents=spent,
            limit_cents=limit, scope="monthly",
        )

    # ------------------------------------------------------------------
    # Helpers — also surfaced via CostEventRepository for service callers.
    # ------------------------------------------------------------------

    async def get_monthly_spend(
        self, agent: AgentRegistration, ref_dt: datetime | None = None,
    ) -> int:
        """Return the agent's spend in the current UTC month (for read-only display)."""
        return await self._sum_for_month(agent.id, ref_dt)
