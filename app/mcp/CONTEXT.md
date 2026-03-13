# MCP Server Adapter

## What This Component Does

The MCP (Model Context Protocol) server is a thin adapter that exposes Calseta's security data and actions to any MCP-compatible AI client (Claude Desktop, Claude Code, Cursor, etc.) without requiring custom API client code. It runs as a standalone process on port 8001, authenticates connections using the same `cai_*` API keys as the REST API, and delegates all business logic to the same service layer and repositories. The server provides read access via MCP resources (URIs that return structured JSON) and write/execute access via MCP tools (callable functions).

## Interfaces

### Server Instance (`server.py`)

```python
from mcp.server.fastmcp import FastMCP
mcp_server = FastMCP(
    name="Calseta",
    auth=_auth_settings,
    token_verifier=CalsetaTokenVerifier(),
    host=settings.MCP_HOST,
    port=settings.MCP_PORT,
)
```

The `mcp_server` instance is imported by all resource and tool modules to register handlers via decorators.

### Resources (Read)

| URI | File | Description |
|---|---|---|
| `calseta://alerts` | `resources/alerts.py` | Recent alerts (last 50) with status, severity, source |
| `calseta://alerts/{uuid}` | `resources/alerts.py` | Full alert with indicators, detection rule, context docs |
| `calseta://alerts/{uuid}/context` | `resources/alerts.py` | Applicable context documents for an alert |
| `calseta://alerts/{uuid}/activity` | `resources/alerts.py` | Activity log (newest-first, max 100 events) |
| `calseta://detection-rules` | `resources/detection_rules.py` | Rule catalog with MITRE mappings and doc summaries |
| `calseta://detection-rules/{uuid}` | `resources/detection_rules.py` | Full rule with complete documentation |
| `calseta://context-documents` | `resources/context_documents.py` | Document catalog (no content -- token-efficient) |
| `calseta://context-documents/{uuid}` | `resources/context_documents.py` | Full document with content and targeting rules |
| `calseta://workflows` | `resources/workflows.py` | Workflow catalog with documentation and approval config |
| `calseta://workflows/{uuid}` | `resources/workflows.py` | Full workflow with code and complete configuration |
| `calseta://metrics/summary` | `resources/metrics.py` | Last 30 days SOC health snapshot |
| `calseta://enrichments/{type}/{value}` | `resources/enrichments.py` | On-demand enrichment (cache-first) |

Resources do NOT enforce per-request scopes (authentication is at connection time via `CalsetaTokenVerifier`). All authenticated connections can read all resources.

### Tools (Write/Execute)

| Tool | File | Required Scope | Description |
|---|---|---|---|
| `post_alert_finding` | `tools/alerts.py` | `alerts:write` | Post an agent analysis finding |
| `update_alert_status` | `tools/alerts.py` | `alerts:write` | Update alert status (with close_classification for Closed) |
| `search_alerts` | `tools/alerts.py` | `alerts:read` | Search alerts by filter criteria |
| `execute_workflow` | `tools/workflows.py` | `workflows:execute` | Execute a workflow (with approval gate based on `approval_mode`: `always`, `agent_only`, or `never`) |
| `enrich_indicator` | `tools/enrichment.py` | `enrichments:read` | Synchronous on-demand enrichment |
| `search_detection_rules` | `tools/detection_rules.py` | `alerts:read` | Search rules by name, MITRE mapping, or source |

Tools enforce per-call scope checks via `check_scope()` from `scope.py`. The `admin` scope is a superscope that passes every check.

### Authentication (`auth.py`)

```python
class CalsetaTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
```

Validates `cai_*` API keys against the same `api_keys` table as the REST API:
1. Check `cai_` prefix and minimum length
2. Look up APIKey row by prefix (first 8 chars)
3. Verify bcrypt hash
4. Check expiry
5. Update `last_used_at`
6. Return `AccessToken(token, client_id=key_prefix, scopes=...)` or `None`

Returns `None` on any failure -- the MCP SDK translates this into an authentication error.

### Scope Enforcement (`scope.py`)

```python
async def check_scope(ctx: Context, session: AsyncSession, *required_scopes: str) -> str | None
```

Returns `None` if the check passes, or a JSON error string if it fails. Tools call this at the start and return the error string directly if non-None. The `admin` scope passes every check.

## Key Design Decisions

1. **Thin adapter -- no independent business logic.** Every resource and tool handler delegates to the same repositories and services used by the REST API. There are zero SQL queries or business rules in the MCP layer. This ensures parity between REST and MCP and eliminates the risk of logic drift.

2. **Resources open their own DB sessions.** Each resource handler uses `async with AsyncSessionLocal() as session:` because the MCP server runs as a standalone process outside FastAPI's DI system. There is no shared request-scoped session.

3. **Token-efficient resource design.** List resources omit large fields: `calseta://context-documents` excludes `content`, `calseta://detection-rules` truncates `documentation` to 200 chars, `calseta://alerts/{uuid}` strips the `raw` key from enrichment results. Single-item resources include full content. This minimizes token consumption when agents scan catalogs.

4. **Tools return JSON strings, not raise exceptions.** MCP tool handlers return error information as JSON strings (`{"error": "..."}`) rather than raising exceptions. This matches the MCP SDK's expectation that tools return string content. The caller (AI agent) parses the response to determine success or failure.

5. **Scope enforcement at tool level, not resource level.** Resources are read-only and available to all authenticated connections. Tools enforce per-call scope checks because they perform writes or trigger executions. This mirrors the REST API pattern where GET endpoints need `*:read` and mutation endpoints need `*:write`.

6. **MCP workflow execution is always agent-triggered.** The `execute_workflow` tool always sets `trigger_type="agent"`, which means workflows with `approval_mode="always"` or `approval_mode="agent_only"` will always enter the approval gate. Only `approval_mode="never"` bypasses the gate via MCP.

## Extension Pattern: Adding a New Resource

1. **Create or add to the appropriate file** in `app/mcp/resources/`:
   ```python
   from app.mcp.server import mcp_server
   from app.db.session import AsyncSessionLocal

   @mcp_server.resource("calseta://my-entity")
   async def list_my_entities() -> str:
       async with AsyncSessionLocal() as session:
           repo = MyEntityRepository(session)
           items, total = await repo.list(page=1, page_size=50)
           return json.dumps({"items": [...], "count": len(items)})
   ```

2. **For parameterized resources**, use `{param}` in the URI:
   ```python
   @mcp_server.resource("calseta://my-entity/{uuid}")
   async def get_my_entity(uuid: str) -> str:
       ...
   ```

3. **Ensure the resource module is imported** in a registration file or `app/mcp/__init__.py` so the decorator runs at startup.

### Adding a New Tool

1. **Create or add to the appropriate file** in `app/mcp/tools/`:
   ```python
   from app.mcp.server import mcp_server
   from app.mcp.scope import check_scope

   @mcp_server.tool()
   async def my_action(param: str, ctx: Context) -> str:
       async with AsyncSessionLocal() as session:
           scope_err = await check_scope(ctx, session, "required:scope")
           if scope_err:
               return scope_err
           # ... business logic via service layer ...
           return json.dumps({"result": "ok"})
   ```

2. **Always call `check_scope()`** at the start for any tool that performs writes or sensitive reads.

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| MCP client gets auth error on connect | Invalid API key, expired key, or wrong prefix | Check `mcp_auth_failure` in logs; verify key starts with `cai_` and is not expired |
| Tool returns `{"error": "Insufficient scope"}` | API key missing required scope | Check `api_keys.scopes` for the key prefix; `admin` scope bypasses all checks |
| Resource returns empty results | DB session opened but no data matches | Check that the MCP server connects to the same database as the API server |
| `AsyncSessionLocal` errors | Database connection issue | MCP server needs `DATABASE_URL` configured correctly; it connects independently from the API process |
| Tool silently returns error JSON instead of raising | This is by design | MCP tools return error information as JSON strings; the AI agent parses and handles errors |

## Test Coverage

There are no dedicated MCP unit tests in the current test suite. The MCP handlers are thin adapters over the same repositories and services tested by:

| Test file | Coverage relevance |
|---|---|
| `tests/integration/test_alerts.py` | Alert CRUD and query logic used by MCP alert resources/tools |
| `tests/integration/test_enrichments.py` | Enrichment service used by `enrich_indicator` tool and enrichment resource |
| `tests/integration/test_workflows.py` | Workflow CRUD and execution used by `execute_workflow` tool |
| `tests/integration/test_detection_rules.py` | Detection rule queries used by search tool and resources |
| `tests/integration/test_context_documents.py` | Context document queries used by context resources |
| `tests/integration/test_auth.py` | API key authentication logic mirrored in `CalsetaTokenVerifier` |
