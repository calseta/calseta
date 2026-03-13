# Workflow Engine and Sandbox

## What This Component Does

The workflow engine executes HTTP automation scripts written in Python in a restricted sandbox. Workflows are `async def run(ctx: WorkflowContext) -> WorkflowResult` functions stored as code strings in the database — Python is the glue layer for constructing HTTP requests, calling external API endpoints via `ctx.http`, and parsing responses. The engine compiles code at runtime, injects a context object with indicator data, alert data, HTTP client, logging, secrets, and integration clients (Okta, Entra), enforces execution timeouts, and captures all results for audit logging. An approval gate intercepts agent-triggered executions of high-risk workflows, requiring human approval before execution proceeds.

### HTTP Automation Pattern

The primary use case for workflows is calling external HTTP endpoints: REST APIs (ServiceNow, Jira, PagerDuty), webhooks (Slack, SOAR platforms), serverless functions (AWS Lambda Function URLs, Azure Logic App triggers), or any service with an HTTP interface. The builtin Okta/Entra workflows are the "batteries included" version of this pattern — they use the same `ctx.http` under the hood, wrapped in typed integration clients for convenience. Custom workflows follow the same pattern with raw HTTP calls.

## Interfaces

### WorkflowContext (`context.py`)

The single parameter injected into every workflow's `run()` function:

```python
@dataclass
class WorkflowContext:
    indicator: IndicatorContext    # type, value, malice, enrichment_results, first_seen, last_seen
    alert: AlertContext | None     # title, severity, source_name, status, tags, raw_payload (None for standalone)
    http: httpx.AsyncClient        # general-purpose HTTP client (timeout = workflow.timeout_seconds)
    log: WorkflowLogger            # ctx.log.info/warning/error/debug or ctx.log("msg")
    secrets: SecretsAccessor       # ctx.secrets.get("ENV_VAR_NAME") -> str | None
    integrations: IntegrationClients  # ctx.integrations.okta / ctx.integrations.entra (may be None)
```

### WorkflowResult (`context.py`)

Return type from every `run()` function:

```python
@dataclass
class WorkflowResult:
    success: bool
    message: str
    data: dict[str, Any]  # arbitrary structured output

    @classmethod
    def ok(cls, message="OK", data=None) -> WorkflowResult: ...
    @classmethod
    def fail(cls, message, data=None) -> WorkflowResult: ...
```

### Integration Clients (`context.py`)

**OktaClient** (available via `ctx.integrations.okta`):
- `revoke_sessions(login)` -- DELETE /users/{id}/sessions
- `suspend_user(login)` -- POST /users/{id}/lifecycle/suspend
- `unsuspend_user(login)` -- POST /users/{id}/lifecycle/unsuspend
- `reset_password(login)` -- POST /users/{id}/lifecycle/reset_password
- `expire_password(login)` -- POST /users/{id}/lifecycle/expire_password

**EntraClient** (available via `ctx.integrations.entra`):
- `revoke_sessions(user_id)` -- POST /users/{id}/revokeSignInSessions
- `disable_account(user_id)` -- PATCH /users/{id} accountEnabled=false
- `enable_account(user_id)` -- PATCH /users/{id} accountEnabled=true
- `reset_mfa(user_id)` -- DELETE all auth methods except password

Both clients manage their own HTTP sessions and auth. They are `None` if credentials are not configured.

### Sandbox (`sandbox.py`)

```python
async def run_workflow_code(code: str, ctx: WorkflowContext, timeout: int) -> WorkflowResult
```

Never raises. Returns `WorkflowResult.fail(...)` for every failure mode: syntax error, missing `run()`, timeout, runtime exception, wrong return type.

### AST Validation (`app/services/workflow_ast.py`)

```python
def validate_workflow_code(code: str) -> list[str]  # empty = valid
```

Enforced at save time (not execution time). Validates:
- Must define `async def run`
- Only allowed imports: safe stdlib subset + `calseta.workflows` / `app.workflows.*`
- Blocked modules: `os`, `subprocess`, `sys`, `importlib`, `socket`, `pickle`, etc.
- Blocked builtins: `exec`, `eval`, `compile`, `__import__`, `open`

### Approval Gate (`approval.py`)

```python
async def create_approval_request(...) -> WorkflowApprovalRequest
async def process_approval_decision(approval_uuid, approved, responder_id, db) -> WorkflowApprovalRequest
```

Gate fires based on `workflow.approval_mode`: `"always"` gates all triggers, `"agent_only"` gates only agent triggers (`trigger_source="agent"`), and `"never"` bypasses the gate entirely.

### Workflow Executor (`app/services/workflow_executor.py`)

```python
async def execute_workflow(workflow, trigger_context, db) -> WorkflowExecutionResult
```

Orchestrates: load indicator from DB, build `WorkflowContext`, call `run_workflow_code()`, return result with log output and duration. Never raises.

## Key Design Decisions

1. **Sandbox uses restricted builtins, not process isolation.** The sandbox blocks `open`, `exec`, `eval`, `compile`, `breakpoint`, `input`, `memoryview` from the builtins namespace but does NOT block `__import__` because Python's import machinery needs it for `import` / `from ... import` statements. Import safety is enforced at save time by AST validation (`validate_workflow_code()`), not at runtime. This was chosen over subprocess isolation for simplicity and performance -- v1 is single-tenant.

2. **Timeout via `asyncio.wait_for()`, not process kill.** `run_workflow_code()` wraps `run_fn(ctx)` in `asyncio.wait_for(timeout)`. This means a CPU-bound workflow that never yields will not be interrupted. Acceptable for v1 since workflows are expected to be I/O-bound (HTTP calls to APIs). Process-level timeout is a v2 consideration.

3. **WorkflowLogger captures to in-memory buffer, not structlog.** Workflow code calls `ctx.log.info(...)` which appends to a list. After execution, `logger.render()` serializes all entries as newline-delimited JSON. This output is stored in `workflow_runs.log_output`. Keeps workflow logs isolated from platform logs and prevents untrusted code from polluting structured log output.

4. **Integration clients are separate from enrichment providers.** `OktaClient` and `EntraClient` in `context.py` are action-oriented (suspend user, revoke sessions) while the Okta and Entra enrichment providers (database-driven, configured in the `enrichment_providers` table) are read-oriented (look up user data). They share API credentials but serve fundamentally different purposes.

5. **Approval gate is in the service layer, not middleware.** The gate check happens in the workflow execute route handler and MCP tool, not as middleware. This allows the gate to access the workflow's `approval_mode` field (`always`/`agent_only`/`never`) and the request's `trigger_source` without additional DB lookups.

### Notifier System (`notifiers/`)

Factory pattern resolving from `APPROVAL_NOTIFIER` env var:

| Value | Class | Behavior |
|---|---|---|
| `none` (default) | `NullApprovalNotifier` | Logs warning; approvers use REST API directly |
| `slack` | `SlackApprovalNotifier` | Posts Block Kit message with Approve/Reject buttons |
| `teams` | `TeamsApprovalNotifier` | Posts Adaptive Card with REST API links (no interactive buttons) |

All notifier methods must never raise. `send_approval_request()` returns an external message ID (Slack `ts`) for threading. `send_result_notification()` posts a follow-up with the execution result.

## Extension Pattern: Adding a New Notifier (e.g. PagerDuty)

1. **Create `app/workflows/notifiers/pagerduty_notifier.py`**:
   ```python
   from app.workflows.notifiers.base import ApprovalNotifierBase, ApprovalRequest

   class PagerDutyApprovalNotifier(ApprovalNotifierBase):
       notifier_name = "pagerduty"

       def __init__(self, cfg):
           self._cfg = cfg

       def is_configured(self) -> bool:
           return bool(getattr(self._cfg, "PAGERDUTY_API_KEY", ""))

       async def send_approval_request(self, request: ApprovalRequest) -> str:
           try:
               # POST to PagerDuty Events API
               ...
               return incident_id  # external ID for threading
           except Exception:
               return ""

       async def send_result_notification(self, request, approved, responder_id) -> None:
           try:
               ...
           except Exception:
               pass  # never raise
   ```

2. **Add to factory** in `app/workflows/notifiers/factory.py`:
   ```python
   if name == "pagerduty":
       from app.workflows.notifiers.pagerduty_notifier import PagerDutyApprovalNotifier
       return PagerDutyApprovalNotifier(cfg)
   ```

3. **Add config** to `app/config.py`: `PAGERDUTY_API_KEY: str = ""`

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| "Workflow code does not define an async function named 'run'" | Missing `async def run(ctx)` | Check workflow code; `def run` (sync) also fails |
| "Workflow code syntax error" | Invalid Python syntax in stored code | AST validation should catch at save time; check `validate_workflow_code()` |
| "Workflow execution timed out after N seconds" | `asyncio.wait_for` expired | Increase `workflow.timeout_seconds`; check if workflow is CPU-bound |
| "import of 'os' is not allowed" | AST validation rejected the code at save time | Only imports in `_ALLOWED_IMPORTS` whitelist are permitted |
| Indicator not found at execution time | Indicator `(type, value)` not in DB | Enrichment pipeline may not have run yet; check `indicator` table |
| `ctx.integrations.okta` is None | `OKTA_DOMAIN` or `OKTA_API_TOKEN` not set | Check env vars; the client is only instantiated when both are present |
| Approval gate not firing | `workflow.approval_mode` is `"never"`, or mode is `"agent_only"` and `trigger_source` is not `"agent"` | Check `approval_mode` value; `"always"` gates all triggers, `"agent_only"` gates only agent triggers |
| Slack notification not sent | `SLACK_BOT_TOKEN` not set or channel misconfigured | Check `slack_approval_send_failed` in logs; verify bot has `chat:write` scope |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/test_workflow_ast.py` | AST validation: allowed imports, blocked imports, blocked builtins, missing `run()`, sync `run()` rejection, `app.workflows.*` imports allowed |
| `tests/test_workflow_executor.py` | Full execution lifecycle: success, failure, timeout, missing indicator, integration client injection |
| `tests/test_builtin_workflows.py` | Built-in workflow code validation and execution with mocked integration clients |
| `tests/test_approval_gate.py` | Approval request creation, decision processing (approve/reject/expire), agent-triggered gating, human bypass |
| `tests/test_agent_trigger.py` | Agent trigger evaluation for approval-gated workflows |
| `tests/integration/test_workflows.py` | CRUD for workflows via REST API; code validation on create/update |
| `tests/integration/test_workflow_runs.py` | Workflow execution via REST; run status tracking |
| `tests/integration/test_workflow_approvals.py` | Approval request creation and decision via REST endpoints |
| `tests/integration/test_approval_callbacks.py` | Slack/Teams callback endpoint testing |
