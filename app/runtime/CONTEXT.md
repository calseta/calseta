# Agent Runtime Engine

## What This Component Does

The agent runtime engine executes managed agents — it makes LLM API calls on behalf of agents registered with `execution_mode = 'managed'`. Given an agent config and an alert (or task), the engine assembles a 6-layer prompt, initializes an LLM provider adapter, runs the tool call loop (send prompt → parse response → if tool_use, execute tool → feed result back → repeat), records `cost_events` for every API call, and persists session state in `agent_task_sessions` for cross-heartbeat continuity. The engine never makes infrastructure decisions — it reads rules from DB (budget, tool tiers, session config) and enforces them deterministically.

## Key Files

| File | Responsibility |
|------|---------------|
| `engine.py` | `AgentRuntimeEngine.run()` — main execution entry point; owns the tool loop and session lifecycle |
| `prompt_builder.py` | `PromptBuilder.build()` — assembles 6-layer prompt from DB state |
| `supervisor.py` | `AgentSupervisor.supervise()` — periodic supervision: timeout and budget checks, no LLM calls |
| `models.py` | `RuntimeContext`, `RuntimeResult`, `BuiltPrompt`, `SupervisionReport` dataclasses |

## Interfaces and Contracts

### AgentRuntimeEngine (`engine.py`)

```python
class AgentRuntimeEngine:
    def __init__(self, db: AsyncSession) -> None: ...  # No queue — uses imported queue functions

    async def run(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
    ) -> RuntimeResult:
        """
        Main execution entry point. Called by run_managed_agent_task (procrastinate task).

        Steps:
        1. Validate agent.execution_mode == 'managed' and agent.llm_integration_id is set
        2. Load LLMIntegration from DB
        3. Resolve or create AgentTaskSession (by agent_id + task_key)
        4. Build prompt via PromptBuilder
        5. Initialize LLMProviderAdapter via factory.get_adapter(integration)
        6. Load agent tools from DB (agent.tool_ids)
        7. Run tool loop (up to MAX_TOOL_ITERATIONS = 50)
        8. Persist session state back to agent_task_sessions
        9. Update assignment.investigation_state with findings/actions
        10. Return RuntimeResult
        """
```

```python
@dataclass
class RuntimeContext:
    alert_id: int | None       # Alert being investigated (None for issue/routine work)
    assignment_id: int | None  # AlertAssignment.id if alert work
    task_key: str              # e.g. "alert:123", "issue:456" — used for session lookup
    heartbeat_run_id: int      # HeartbeatRun.id for cost attribution

@dataclass
class RuntimeResult:
    success: bool
    findings: list[dict]
    actions_proposed: list[dict]
    total_cost_cents: int
    input_tokens: int
    output_tokens: int
    session_key: str | None
    error: str | None
    iterations: int
```

### PromptBuilder (`prompt_builder.py`)

```python
class PromptBuilder:
    def __init__(self, db: AsyncSession) -> None: ...

    async def build(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
        session: AgentTaskSession | None,
    ) -> BuiltPrompt:
        """Returns BuiltPrompt with system_prompt, messages, layer_tokens, total_tokens_estimated."""
```

**Final structure:**
```
system_prompt = layer1 + layer2 + layer3 + layer6   (in system field of LLM call)
messages      = [layer4_user_msg] + layer5_history   (in messages list)
```

## The 6-Layer Prompt Construction System

### Layer 1 — Identity + Instructions (system prompt, always present)

Parts concatenated with `\n\n---\n\n`:
1. `agent.system_prompt` (the agent's base role definition)
2. Per-agent instruction files from `agent.instruction_files` JSONB array (embedded content)
3. Global instruction files with `scope = f"role:{agent.role}"` from `agent_instruction_files` table, ordered by `inject_order ASC`
4. Global instruction files with `scope = "global"` from `agent_instruction_files` table, ordered by `inject_order ASC`

### Layer 2 — Methodology (system prompt, optional)

`agent.methodology` wrapped in `<methodology>...</methodology>` tags. Skipped if `agent.methodology` is None.

### Layer 3 — Knowledge Base Context (system prompt, token-budget capped)

Pages injected as `<context_document title="..." slug="..." updated="YYYY-MM-DD">…body…</context_document>` blocks.

**What is included:** KB pages where `KBPageRepository.get_injectable_pages(agent_uuid, agent_role)` returns a result. Injectable pages are those with `inject_scope` matching one of: `'global'`, `f'role:{agent.role}'`, or `f'agent:{agent.uuid}'`.

**Budget:** 15% of context window (`context_window * 0.15` tokens). Pinned pages (`page.inject_pinned = True`) are always included regardless of budget. Non-pinned pages are skipped once the budget is exhausted.

**Token estimation:** `page.token_count` if stored, otherwise `len(page.body) // 4`.

**On failure:** Any exception in layer 3 is caught and logged as `prompt_builder.layer3_kb_failed`. The prompt build continues with an empty layer 3 — it never propagates.

### Layer 4 — Alert/Task Context (first user message)

Built as a `<alert_context>\n{json.dumps(alert_data)}\n</alert_context>` user message. Contains:
- Alert fields: uuid, title, severity, status, source_name, description, occurred_at, enrichment_status, is_enriched, tags, agent_findings
- Detection rule: uuid, name, documentation, mitre_tactics, mitre_techniques (if linked)
- Indicators: up to 50, each with type, value, malice, first_seen, last_seen, enrichment_results
- assignment_id (if present)

Skipped (returns None) if `context.alert_id is None`.

### Layer 5 — Session State (messages list)

Three cases, in priority order:
1. **Compacted session** — `session_params["session_handoff_markdown"]` is set: inject handoff summary + alert context as a single user message. Session history is discarded. This is the post-compaction case.
2. **Resuming session** — `session_params["messages"]` is set: use the existing conversation history directly. Alert context is NOT re-injected (it's already in history).
3. **Fresh session** — no session or empty session_params: only the layer 4 alert context user message.

### Layer 6 — Runtime Checkpoint + Agent Memory (system prompt, appended last)

**Checkpoint block** (`<runtime_checkpoint>…</runtime_checkpoint>`):
- Budget line: `Budget: $X.XX of $Y.YY spent (Z% used).` or `Budget: unlimited` if `budget_monthly_cents == 0`
- Warning line appended if `spent / budget > 0.80`: `⚠️ Budget WARNING: approaching limit.`

**Memory block** (`<agent_memory>…</agent_memory>`): KB pages from the agent's memory folder (`/memory/agents/{agent.id}/`, status=`published`).

- **Budget:** 5% of context window (`context_window * 0.05` tokens)
- **Sort order:** non-stale pages first, then by `updated_at DESC` within each group
- **Staleness detection:** page is stale if `(now - page.updated_at).total_seconds() / 3600 > page.metadata_["staleness_ttl_hours"]`. Pages without `staleness_ttl_hours` in metadata are never stale.
- **Stale prefix:** `[STALE — last updated {hours_ago} hours ago]` prepended to the body
- **Format:** `<memory title="…" slug="…" stale="true|false">…body…</memory>`
- **On failure:** caught, logged as `prompt_builder.memory_injection_failed`, returns empty string

## Budget Enforcement

Budget enforcement happens in **two places**:

**1. Engine loop (per-alert cap, synchronous):**
After each LLM API call, the engine checks `cost_cents` against `agent.max_cost_per_alert_cents`. If exceeded, it raises `BudgetExceededError`. This is caught by the loop, recorded as a `cost.hard_stop` activity event, and returned as `RuntimeResult(success=False, error="budget_exceeded")`.

**2. AgentSupervisor (monthly cap, periodic):**
Runs every 30 seconds. Checks `agent.spent_monthly_cents` against `agent.budget_monthly_cents` for all in-progress assignments. If monthly cap is hit, releases the assignment and marks it as `budget_stopped`. This is coarse-grained (doesn't stop mid-LLM-call) — it prevents the next heartbeat from starting new work.

## Session Compaction

**Trigger:** When `total_input_tokens + total_output_tokens` in the current session exceeds **80% of the model's context window**, the engine triggers compaction.

**What happens:**
1. Engine calls the LLM with the full conversation history + a compaction instruction
2. LLM generates a `session_handoff_markdown` summary covering: investigation progress, findings so far, pending questions, recommended next steps
3. Summary is stored in `agent_task_sessions.session_params["session_handoff_markdown"]`
4. Conversation `messages` list is cleared from `session_params`
5. Token counters reset

**Next heartbeat:** `PromptBuilder._build_messages()` detects `session_handoff_markdown` and uses the compacted-session path (Layer 5, case 1). The full history is gone — only the summary is injected.

## Design Decisions

**Why a tool loop rather than a single prompt + response?**
Modern LLM use cases require multiple rounds: send prompt → receive tool_use → execute tool → feed result → send next. The engine owns this loop. Each iteration is one LLM API call; cost is recorded after each call. The loop exits when `stop_reason == "end_turn"` or `MAX_TOOL_ITERATIONS` (50) is reached.

**Why persist session state in `agent_task_sessions`?**
Multi-wave investigations span multiple heartbeat invocations. Without session persistence, every heartbeat restarts from scratch (wasting tokens on re-establishing context). Session state stores conversation history (`session_params["messages"]`) so the agent resumes mid-investigation.

**Why is layer 6 in the system prompt, not as a user message?**
Budget status and agent memory are meta-context about the agent itself, not about the task. Keeping them in the system prompt (which the LLM treats as persistent instructions) versus the user message (which the LLM treats as turn-by-turn input) produces more reliable adherence.

**Why is compaction at 80%, not 100%?**
The LLM needs headroom to generate a complete handoff summary. At 100% context, the compaction call itself would exceed the limit. 80% leaves ~20% for the compaction LLM call.

## Extension Pattern

**To add a new tool:**
1. Register in `app/seed/builtin_tools.py` with `handler_ref = "calseta:my_tool"`
2. Add handler in `app/integrations/tools/dispatcher.py:_execute_handler()`:
   ```python
   if tool.handler_ref == "calseta:my_tool":
       return await self._my_handler(tool_input)
   ```
3. No engine changes needed — the tool loop is tool-agnostic.

**To add a new LLM provider:**
- See `app/integrations/llm/CONTEXT.md` — add adapter, register in factory
- The engine calls `get_adapter(integration)` from the factory; no engine changes

**To add a new prompt layer:**
- Add a `_build_layer7_…()` method to `PromptBuilder`
- Decide whether it goes in `system_prompt` (persistent meta) or `messages` (turn input)
- Append to the relevant assembly in `build()`

## Common Failure Modes

**`BudgetExceededError` mid-investigation**
`max_cost_per_alert_cents` hit before agent finished. Check `cost_events` for this alert (via `GET /v1/costs/by-alert`). Raise the per-alert budget on the agent (`PATCH /v1/agents/{uuid}`) or accept the partial result.

**Session not resuming (agent restarts from scratch every heartbeat)**
`agent_task_sessions` row exists but `session_params` is empty or messages missing. For `AnthropicAdapter`: messages stored in `session_params["messages"]` — if null, session was not saved correctly. Check for exceptions in the heartbeat run log. Likely cause: `_save_session()` threw before commit.

**Layer 3 (KB) always empty even with pages configured**
`KBPageRepository.get_injectable_pages()` returned nothing. Check that pages have the correct `inject_scope` value (`'global'`, `'role:threat_intel'`, or `'agent:{uuid}'`) and `status = 'published'`.

**Memory not injecting**
Pages at `/memory/agents/{id}/` not found or all stale. Check folder path (`agent.id`, not `agent.uuid`). Check `status = 'published'` on pages. Stale pages are still injected with the `[STALE]` prefix unless the memory budget is exhausted.

**Tool call returns `ToolForbiddenError`**
Agent called a tool not in `agent.tool_ids`, or tool has `tier = 'forbidden'`. Update `tool_ids` via `PATCH /v1/agents/{uuid}`. Config error, not a runtime error.

**Engine hangs (heartbeat run stays `running` indefinitely)**
`AgentSupervisor` detects this after `agent.timeout_seconds` and kills the run. Most common cause: LLM API call that never returns. Check for `asyncio.TimeoutError` in heartbeat run logs.

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
    └── mock_alerts.json        # Test alert payloads
```

Mock strategy: patch `LLMProviderAdapter.create_message` at the interface boundary — never call real LLM APIs in CI.
