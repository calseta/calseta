"""
Agent topology routes — computed graph of the agent fleet.

GET    /v1/topology                Full topology (all nodes + delegation edges)
GET    /v1/topology/routing        Routing paths only (agents with trigger config)
GET    /v1/topology/delegation     Delegation paths only (orchestrators + specialists)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.schemas.common import DataResponse
from app.schemas.topology import TopologyGraph
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/topology", tags=["topology"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]


@router.get("", response_model=DataResponse[TopologyGraph])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_topology(
    request: Request,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[TopologyGraph]:
    """Return the full agent fleet topology graph.

    Nodes represent registered agents. Edges represent delegation relationships
    (orchestrator→specialist). Use this to understand how agents are connected.
    """
    svc = TopologyService(db)
    graph = await svc.compute_topology()
    return DataResponse(data=graph, meta={})


@router.get("/routing", response_model=DataResponse[TopologyGraph])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_routing_topology(
    request: Request,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[TopologyGraph]:
    """Return only agents that have alert routing configuration.

    Shows which agents are configured to receive alerts based on source
    and severity trigger filters. No edges — just routing-enabled nodes.
    """
    svc = TopologyService(db)
    graph = await svc.compute_routing_graph()
    return DataResponse(data=graph, meta={})


@router.get("/delegation", response_model=DataResponse[TopologyGraph])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_delegation_topology(
    request: Request,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[TopologyGraph]:
    """Return only agents involved in delegation relationships.

    Shows orchestrator agents and their specialist sub-agents, with
    delegates_to edges connecting them. Agents with no delegation
    relationships are excluded.
    """
    svc = TopologyService(db)
    graph = await svc.compute_delegation_graph()
    return DataResponse(data=graph, meta={})
