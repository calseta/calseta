"""
Calseta MCP Server — Model Context Protocol adapter.

Thin adapter over the REST API's service layer. Exposes security data as
MCP resources and actions as MCP tools so any MCP-compatible client (Claude
Desktop, Claude Code, Cursor, etc.) can access Calseta without custom API
client code.

This module creates the ``FastMCP`` server instance with API key
authentication. Resources and tools are registered in Wave 7 chunks 7.2–7.5.
"""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.mcp.auth import CalsetaTokenVerifier

# AuthSettings is required by the SDK when a token_verifier is provided.
# issuer_url / resource_server_url are OAuth metadata fields; our
# CalsetaTokenVerifier does the actual API key validation, not OAuth.
_base_url = settings.CALSETA_BASE_URL.rstrip("/")
_mcp_url = f"http://{settings.MCP_HOST}:{settings.MCP_PORT}"

_auth_settings = AuthSettings(
    issuer_url=_mcp_url,
    resource_server_url=_mcp_url,
)

mcp_server = FastMCP(
    name="Calseta AI",
    instructions=(
        "Calseta AI is a SOC data platform. Use resources to read security "
        "alerts, detection rules, context documents, workflows, and metrics. "
        "Use tools to post findings, update alert status, execute workflows, "
        "and enrich indicators."
    ),
    auth=_auth_settings,
    token_verifier=CalsetaTokenVerifier(),
    host=settings.MCP_HOST,
    port=settings.MCP_PORT,
)
