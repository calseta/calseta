# Tool Dispatcher

## What This Component Does

The tool dispatcher routes managed agent tool calls to the correct built-in handler. When the LLM returns a `tool_use` content block, the engine passes the tool name and input to `ToolDispatcher.dispatch()`. The dispatcher looks up the tool in the `agent_tools` table, enforces tier permissions and agent assignment, then executes the tool's `handler_ref` implementation. Every built-in handler calls into the real service/repository layer and returns a structured dict.

## Interfaces

### ToolDispatcher (`dispatcher.py`)

```python
class ToolDispatcher:
    def __init__(self, db: AsyncSession, agent: AgentRegistration) -> None: ...

    async def dispatch(self, tool_id: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call.

        Steps:
          1. Look up tool by id in the agent_tools table
          2. Verify the tool is in agent.tool_ids
          3. Enforce tier: forbidden → ToolForbiddenError
          4. Enforce tier: requires_approval → ToolRequiresApprovalError
          5. Execute via handler_ref for safe/managed tools
          6. Return result dict
        """
```

### Errors

| Exception | When raised |
|---|---|
| `ToolNotFoundError` | Tool id does not exist in `agent_tools` table |
| `ToolNotAssignedError` | Tool exists but is not in `agent.tool_ids` |
| `ToolForbiddenError` | `tool.tier == "forbidden"` or `tool.is_active == False` |
| `ToolRequiresApprovalError` | `tool.tier == "requires_approval"` (approval gate not bypassed) |

All errors bubble up to the engine's tool loop, which catches them and returns a structured `{"type": "tool_result", "is_error": True, "content": "..."}` message back to the LLM.

### Built-in Handlers

Handler functions follow the signature `async (db, agent, tool_input) -> dict`. They are registered in `_BUILTIN_HANDLERS`:

| handler_ref | Operation | Returns |
|---|---|---|
| `calseta:get_alert` | Fetch alert by UUID | `{status, data: {uuid, title, severity, ...}}` |
| `calseta:search_alerts` | Search alerts by status/severity | `{status, data: {total, alerts: [...]}}` |
| `calseta:get_enrichment` | Get indicator enrichment by type+value | `{status, data: {indicator_type, value, malice, enrichment_results}}` |
| `calseta:post_finding` | Record agent finding on alert | `{status, data: {alert_uuid, classification, confidence, recorded}}` |
| `calseta:update_alert_status` | Transition alert status | `{status, data: {alert_uuid, status}}` |
| `calseta:get_detection_rule` | Fetch detection rule by UUID | `{status, data: {uuid, name, documentation, mitre_*}}` |
| `calseta:list_context_documents` | List context docs applicable to alert | `{status, data: {documents: [{uuid, title, snippet}]}}` |
| `calseta:execute_workflow` | Execute workflow (tier=requires_approval — never reaches handler) | stub |

## Key Design Decisions

**Why DB-driven tool registry rather than hardcoded?**
Tool tiers (`safe`, `managed`, `requires_approval`, `forbidden`) are operator-configurable at runtime via `PATCH /v1/tools/{id}`. An operator can downgrade a dangerous tool to `forbidden` without a code deploy. The `agent_tools` table is the runtime gate — the handler map in `_BUILTIN_HANDLERS` is the implementation layer.

**Why is `execute_workflow` in `requires_approval` tier?**
Workflows can take destructive actions (block IPs, disable accounts). The tier system ensures an agent cannot autonomously execute workflows without operator approval, even if the workflow tool is in `agent.tool_ids`. The `ToolRequiresApprovalError` is raised before the handler is ever called.

**Why check `tool_ids` before tier?**
Defense in depth. An agent can only call tools explicitly listed in its `tool_ids`. This prevents a misconfigured tool tier from accidentally granting access to a tool the operator never assigned to this agent.

**Handler function signature vs. class-based handlers**
Module-level async functions are simpler and testable in isolation — no need to instantiate a class per tool call. Each handler receives `(db, agent, tool_input)` and returns a dict. Full service wiring (e.g., calling the EnrichmentService rather than a raw repo query) is in scope but deferred to avoid over-engineering at Phase 1.

## Extension Pattern

To add a new built-in tool:

1. Seed the tool in `app/seed/builtin_tools.py`:
   ```python
   AgentToolCreate(
       id="block_ip",
       display_name="Block IP Address",
       description="Add an IP to the block list via the firewall integration.",
       tier=AgentToolTier.MANAGED,
       category=AgentToolCategory.RESPONSE,
       handler_ref="calseta:block_ip",
       input_schema={"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]},
   )
   ```

2. Add the handler function in `dispatcher.py`:
   ```python
   async def _handle_block_ip(
       db: AsyncSession,
       agent: AgentRegistration,
       tool_input: dict[str, Any],
   ) -> dict[str, Any]:
       ip = tool_input.get("ip", "")
       # call service layer
       return {"status": "ok", "data": {"ip": ip, "blocked": True}}
   ```

3. Register it in `_BUILTIN_HANDLERS`:
   ```python
   _BUILTIN_HANDLERS: dict[str, Any] = {
       ...
       "block_ip": _handle_block_ip,
   }
   ```

4. No changes to `ToolDispatcher.dispatch()` or the engine's tool loop.

For external/custom tools (non-`calseta:` handler_ref), the dispatcher currently returns a structured error. Phase 6 will add an HTTP dispatch path for `handler_ref = "http:<url>"`.

## Common Failure Modes

**`ToolNotFoundError` on every call**
The tool was not seeded. Run `make migrate` to apply migrations, then check that `app/seed/builtin_tools.py` is called at startup. The `agent_tools` table should have rows for all built-in tools.

**`ToolNotAssignedError` despite correct `tool_ids`**
`agent.tool_ids` is a `TEXT[]` PostgreSQL array. Verify the value with `GET /v1/agents/{uuid}`. A common mistake is passing a JSON array of objects instead of an array of string IDs.

**`ToolRequiresApprovalError` blocking agent progress**
Workflow execution is gated behind the approval system. If the agent needs to execute workflows autonomously, use the `workflow_approval` APIs to pre-approve, or lower the tool tier (not recommended for production).

**Handler returns `{"status": "error"}`**
Check the `error` key in the response. Common causes: invalid UUID format in input, entity not found, or validation failure in the handler. The LLM will see this error as the tool result and may retry or report it as a finding.

**`unimplemented_builtin_handler` log line**
The `handler_ref` in the DB references an operation not in `_BUILTIN_HANDLERS`. Either the tool row has a typo in `handler_ref`, or the handler was never added. Fix the `handler_ref` value via `PATCH /v1/tools/{id}`.

## Test Coverage

```
tests/unit/test_tool_dispatcher.py
  - dispatch() happy path for each built-in handler
  - ToolNotFoundError when tool_id does not exist
  - ToolNotAssignedError when tool not in agent.tool_ids
  - ToolForbiddenError for forbidden tier and inactive tools
  - ToolRequiresApprovalError for requires_approval tier

tests/integration/agent_control_plane/test_phase1_managed_agent.py
  - End-to-end tool call: engine calls dispatcher → handler → DB → result returned to LLM
  - Tool error handling: handler raises → engine wraps as is_error tool_result
```
