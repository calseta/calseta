"""
Workflow execution service.

Orchestrates the full lifecycle of a single workflow execution:
  1. Loads indicator (and alert if applicable) from the DB
  2. Builds the indicator/alert payload for the isolated runner
  3. Delegates to ``run_workflow_isolated`` (subprocess runtime, S1)
  4. Returns a WorkflowExecutionResult for audit logging

This module does NOT write to the database — that is the caller's responsibility
(WorkflowRun creation and update is done by the route handler / queue task).

Never raises. All errors are captured in WorkflowExecutionResult.result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.workflow import Workflow
from app.repositories.indicator_repository import IndicatorRepository
from app.workflows.context import (
    AlertContext,
    EntraClient,
    IndicatorContext,
    IntegrationClients,
    OktaClient,
    TriggerContext,
    WorkflowLogger,
    WorkflowResult,
)
from app.workflows.runner import (
    run_workflow_isolated,
    serialize_alert,
    serialize_indicator,
)

# ---------------------------------------------------------------------------
# WorkflowExecutionResult
# ---------------------------------------------------------------------------


@dataclass
class WorkflowExecutionResult:
    """
    Output from execute_workflow().

    Callers (route handler or queue task) persist this into workflow_runs.
    """

    result: WorkflowResult
    log_output: str
    duration_ms: int
    code_version_executed: int


# ---------------------------------------------------------------------------
# Integration client factory
# ---------------------------------------------------------------------------


def _build_integrations() -> IntegrationClients:
    """Instantiate integration clients based on configured env vars."""
    okta: OktaClient | None = None
    if settings.OKTA_DOMAIN and settings.OKTA_API_TOKEN:
        okta = OktaClient(
            domain=settings.OKTA_DOMAIN,
            api_token=settings.OKTA_API_TOKEN,
        )

    entra: EntraClient | None = None
    if settings.ENTRA_TENANT_ID and settings.ENTRA_CLIENT_ID and settings.ENTRA_CLIENT_SECRET:
        entra = EntraClient(
            tenant_id=settings.ENTRA_TENANT_ID,
            client_id=settings.ENTRA_CLIENT_ID,
            client_secret=settings.ENTRA_CLIENT_SECRET,
        )

    return IntegrationClients(okta=okta, entra=entra)


# ---------------------------------------------------------------------------
# Alert context builder
# ---------------------------------------------------------------------------


async def _build_alert_context(
    alert_id: int | None, db: AsyncSession
) -> AlertContext | None:
    """Load alert from DB and convert to AlertContext. Returns None if not found or no alert_id."""
    if alert_id is None:
        return None

    from app.repositories.alert_repository import AlertRepository

    repo = AlertRepository(db)
    alert = await repo.get_by_id(alert_id)
    if alert is None:
        return None

    return AlertContext(
        uuid=alert.uuid,
        title=alert.title,
        severity=alert.severity,
        source_name=alert.source_name,
        status=alert.status,
        occurred_at=alert.occurred_at,
        tags=list(alert.tags or []),
        raw_payload=dict(alert.raw_payload or {}),
    )


# ---------------------------------------------------------------------------
# execute_workflow
# ---------------------------------------------------------------------------


async def execute_workflow(
    workflow: Workflow,
    trigger_context: TriggerContext,
    db: AsyncSession,
) -> WorkflowExecutionResult:
    """
    Execute a workflow and return the result.

    Args:
        workflow:        The Workflow ORM instance (provides code, timeout, code_version).
        trigger_context: What triggered this execution (indicator, alert link, trigger_source).
        db:              Async DB session for loading indicator and alert data.

    Returns:
        WorkflowExecutionResult — never raises.
    """
    logger = WorkflowLogger()
    start_ms = int(time.monotonic() * 1000)

    # Load indicator
    indicator_repo = IndicatorRepository(db)
    indicator = await indicator_repo.get_by_type_and_value(
        trigger_context.indicator_type,
        trigger_context.indicator_value,
    )

    if indicator is None:
        result = WorkflowResult.fail(
            f"Indicator ({trigger_context.indicator_type}, "
            f"'{trigger_context.indicator_value}') not found in database"
        )
        return WorkflowExecutionResult(
            result=result,
            log_output=logger.render(),
            duration_ms=int(time.monotonic() * 1000) - start_ms,
            code_version_executed=workflow.code_version,
        )

    indicator_ctx = IndicatorContext(
        uuid=indicator.uuid,
        type=indicator.type,
        value=indicator.value,
        malice=indicator.malice,
        is_enriched=indicator.is_enriched,
        enrichment_results=_safe_dict(indicator.enrichment_results),
        first_seen=indicator.first_seen,
        last_seen=indicator.last_seen,
        created_at=indicator.created_at,
        updated_at=indicator.updated_at,
    )

    alert_ctx = await _build_alert_context(trigger_context.alert_id, db)

    # Integrations object retained for in-process compatibility paths but
    # not currently proxied to the isolated runner (Okta/Entra clients run
    # in the parent — S1 v1 ships proxied http+secrets+log only).  Future
    # iterations will route integration calls through additional IPC ops.
    _ = _build_integrations()

    # Wave 5 / S1 — execute the workflow in an isolated subprocess.  The
    # parent (this process) handles HTTP requests with the same SSRF gate,
    # so SSRF protection is preserved transparently.
    async with httpx.AsyncClient(
        timeout=float(workflow.timeout_seconds),
    ) as http:
        ctx_payload: dict[str, Any] = {
            "indicator": serialize_indicator(indicator_ctx),
            "alert": serialize_alert(alert_ctx),
            # S3: per-workflow secret allowlist; the parent's ``secret.get``
            # IPC handler honors it (plus the global denylist) before reading
            # ``os.environ`` on the child's behalf.
            "allowed_secrets": list(workflow.allowed_secrets or []),
        }
        result = await run_workflow_isolated(
            code=workflow.code,
            ctx_payload=ctx_payload,
            timeout_seconds=workflow.timeout_seconds,
            memory_mb=settings.WORKFLOW_MAX_MEMORY_MB,
            http_client=http,
        )

    # The isolated runner mirrors the child's log buffer back into
    # ``result.data["__log_buffer"]`` so the caller can persist it.
    log_output = ""
    if isinstance(result.data, dict):
        buffered = result.data.pop("__log_buffer", None)
        if isinstance(buffered, str):
            log_output = buffered
        # Strip the metadata key from the public ``data`` dict — runner-only.
        result.data.pop("__metadata", None)
    if not log_output:
        log_output = logger.render()

    duration_ms = int(time.monotonic() * 1000) - start_ms
    return WorkflowExecutionResult(
        result=result,
        log_output=log_output,
        duration_ms=duration_ms,
        code_version_executed=workflow.code_version,
    )


def _safe_dict(value: Any) -> dict[str, Any] | None:
    """Return a dict copy or None for JSON fields that may be None."""
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    return None
