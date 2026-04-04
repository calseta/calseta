# Agent Runtime Engine

## What This Component Does

The agent runtime engine executes managed agents — it makes LLM API calls on behalf of agents registered with `execution_mode = 'managed'`. Given an agent config and an alert (or task), the engine assembles a 6-layer prompt, initializes an LLM provider adapter, runs the tool call loop (send prompt → parse response → if tool_use, execute tool → feed result back → repeat), records `cost_events` for every API call, and persists session state in `agent_task_sessions` for cross-heartbeat continuity. The engine never makes infrastructure decisions — it reads rules from DB (budget, tool tiers, session config) and enforces them deterministically.

## Interfaces

### AgentRuntimeEngine (`engine.py`)

```python
class AgentRuntimeEngine:
    def __init__(self, db: AsyncSession, queue: TaskQueueBase) -> None: ...

    async def run(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
    ) -> RuntimeResult:
        """
        Main execution entry point. Called by run_managed_agent_task.
        
        1. Load LLMIntegration from agent.llm_integration_id
        2. Resolve session (resume or create) from agent_task_sessions
        3. Construct 6-layer prompt via PromptBuilder
        4. Initialize LLMProviderAdapter via factory.get_adapter()
        5. Run tool loop: create_message → parse → execute tools → repeat
        6. Record cost_events after every LLM call
        7. Persist session_params + investigation_state
        8. Return RuntimeResult
        """
```

```python
@dataclass
class RuntimeContext:
    alert_id: int | None       # Alert being investigated (None for issue/routine work)
    assignment_id: int | None  # AlertAssignment.id if alert work
    task_key: str              # e.g. "alert:123", "issue:456"
    heartbeat_run_id: int      # HeartbeatRun.id for cost attribution

@dataclass
class RuntimeResult:
    success: bool
    findings: list[dict]
    actions_proposed: list[dict]
    total_cost_cents: int
    input_tokens: int
    output_tokens: int
    session_id: str | None     # For ClaudeCodeAdapter session continuity
    error: str | None
```

### PromptBuilder (`prompt_builder.py`)

Constructs the 6-layer prompt:

```python
class PromptBuilder:
    async def build(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
        session: AgentTaskSession | None,
    ) -> BuiltPrompt:
        """Returns assembled system prompt + messages list + token estimate."""
```

Layer order (concatenated into system prompt, then context as user messages):
```
Layer 1: agent.system_prompt
         + agent.instruction_files (per-agent, in order)
         + global agent_instruction_files scoped to agent.role (by inject_order)
         + global agent_instruction_files scoped 'global' (by inject_order)
Layer 2: agent.methodology (injected as <methodology>...</methodology> block)
Layer 3: KB pages with inject_scope matching this agent/role (stub in Phase 1 — empty list)
Layer 4: Alert/task context (enriched alert payload, assignment details, prior findings)
Layer 5: Session state (session_handoff_markdown if compacted, or resume from session_params)
Layer 6: Runtime checkpoint (budget status, time elapsed, severity flags)
```

### ToolDispatcher (`app/integrations/tools/dispatcher.py`)

Used by the engine for tool call execution. See `app/integrations/tools/CONTEXT.md`.

### AgentSupervisor (`supervisor.py`)

Periodic Procrastinate task (every 30s):
```python
class AgentSupervisor:
    async def supervise(self) -> SupervisionReport:
        """Checks all active assignments for: stuck agents, budget breach, stall, time limit."""
```

Runs in the worker process. Never makes LLM calls. All decisions are deterministic rules against DB state.

## Key Design Decisions

**Why a tool loop rather than a single prompt + response?**
Modern LLM use cases (tool-augmented agents) require multiple rounds of: send prompt → receive tool_use → execute tool → feed result → send next prompt. The engine owns this loop. Each iteration is one LLM API call; cost is recorded after each call. The loop exits when `stop_reason == "end_turn"` or the agent produces a text response without tool calls.

**Why persist session state in `agent_task_sessions`?**
Multi-wave investigations span multiple heartbeat invocations (the agent picks up an alert, does some work, the process exits, and resumes on the next heartbeat). Without session persistence, every heartbeat restarts from scratch (wasting tokens on re-establishing context). Session state stores the conversation history reference (for `ClaudeCodeAdapter`: `session_id`; for `AnthropicAdapter`: conversation messages) so the agent resumes mid-investigation.

**Session compaction at 80% context window**
When `total_input_tokens + total_output_tokens` exceeds 80% of the model's context window, the engine triggers compaction: calls the LLM to generate a handoff summary, stores it as `session_handoff_markdown` in `session_params`, resets token counters. Next heartbeat injects the summary as the first user message instead of the full history. This prevents context overflow in long investigations.

**Layer 3 (KB) is stubbed in Phase 1**
The Knowledge Base system (Phase 6) is not yet built. `PromptBuilder._build_layer3_kb()` returns an empty list. The prompt construction code is structured to accept the KB output when Phase 6 ships without changes to the engine.

**Budget enforcement is in the engine loop, not just the supervisor**
After each LLM call, the engine checks `cost_cents` against `agent.max_cost_per_alert_cents`. If exceeded, it raises `BudgetExceededError`, which is caught and recorded as a `cost.hard_stop` activity event. The supervisor handles monthly budget enforcement (less time-sensitive).

## Extension Pattern

To add a new managed agent capability (e.g., a new tool that calls an external API):

1. Register the tool in `app/seed/builtin_tools.py` with a `handler_ref` like `calseta:my_new_tool`.
2. Add the handler in `app/integrations/tools/dispatcher.py` under `_execute_handler()`:
   ```python
   if tool.handler_ref == "calseta:my_new_tool":
       result = await self._call_my_service(tool_input)
       return {"result": result}
   ```
3. Add the service method to the appropriate service class.
4. No changes needed to the engine itself — the tool loop is tool-agnostic.

To add a new LLM provider:
- See `app/integrations/llm/CONTEXT.md` — add adapter, register in factory.
- The engine uses `get_adapter(integration)` from the factory; no engine changes needed.

## Common Failure Modes

**`BudgetExceededError` mid-investigation**
`max_cost_per_alert_cents` was hit before the agent finished. Check `cost_events` for this alert (via `GET /v1/costs/by-alert`). Either raise the per-alert budget on the agent (`PATCH /v1/agents/{uuid}`) or accept the partial investigation and manually close the assignment.

**Session not resuming (agent restarts from scratch every heartbeat)**
`agent_task_sessions` row exists but `session_params` is empty or `session_handoff_markdown` is stale. For `ClaudeCodeAdapter`: the `session_id` must be persisted across heartbeats. Check that the worker process has write access to `CALSETA_DATA_DIR`. For `AnthropicAdapter`: conversation messages are stored in `session_params` — if the JSONB field is null, the session was not saved. Check for exceptions in the heartbeat run logs.

**Tool call returns `ToolForbiddenError`**
The agent attempted to call a tool not in its `tool_ids` list, or the tool has `tier = 'forbidden'`. Update the agent's `tool_ids` via `PATCH /v1/agents/{uuid}`. This is a config error, not a runtime error.

**Engine hangs (heartbeat run stays `running` indefinitely)**
`AgentSupervisor` will detect this after `agent.timeout_seconds` and kill the run. The most common cause is an LLM API call that never returns — check for `asyncio.TimeoutError` in heartbeat run logs. `max_tokens` should be set on the integration to prevent excessively long responses that never complete.

## Test Coverage

```
tests/integration/agent_control_plane/
├── test_phase1_managed_agent.py
│   - Full run: checkout → LLM call (mocked AnthropicAdapter) → tool loop
│     → finding posted → cost recorded → session state persisted
│   - Session compaction trigger: token threshold hit → handoff summary generated
│   - Budget hard stop: max_cost_per_alert_cents exceeded mid-loop
│   - Tool tier enforcement: safe/managed execute, forbidden blocked
│
├── test_phase1_claude_code_adapter.py
│   - ClaudeCodeAdapter subprocess invocation (mocked asyncio.create_subprocess_exec)
│   - NDJSON parsing: system/assistant/result events
│   - session_id round-trip across two heartbeats
│   - test_environment() with mock CLI response
│
└── fixtures/
    ├── mock_llm_responses.py   # Canned LLM response sequences
    └── mock_alerts.json        # 20 test alerts
```

Mock strategy: patch `LLMProviderAdapter.create_message` at the interface boundary — never call real LLM APIs in CI. The `mock_llm_responses.py` fixture provides canned sequences covering: text completion, tool_use → result → text completion, budget exceeded mid-loop, session compaction trigger.
