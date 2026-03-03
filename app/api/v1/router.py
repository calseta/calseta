"""
v1 API router — aggregates all versioned sub-routers.

Add new route modules here as they are built in subsequent waves.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    alerts,
    api_keys,
    approvals,
    context_documents,
    detection_rules,
    enrichment_providers,
    enrichments,
    indicator_mappings,
    indicators,
    ingest,
    metrics,
    sources,
    workflow_approvals,
    workflows,
)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(api_keys.router)
v1_router.include_router(alerts.router)
v1_router.include_router(ingest.router)
v1_router.include_router(indicator_mappings.router)
v1_router.include_router(indicators.router)
v1_router.include_router(detection_rules.router)
v1_router.include_router(enrichments.router)
v1_router.include_router(enrichment_providers.router)
v1_router.include_router(context_documents.router)
v1_router.include_router(workflows.router)
v1_router.include_router(workflows.workflow_runs_router)
v1_router.include_router(workflow_approvals.router)
v1_router.include_router(approvals.router)
v1_router.include_router(agents.router)
v1_router.include_router(sources.router)
v1_router.include_router(metrics.router)
