# Action Integration System

## What This Component Does

The action integration system executes approved agent response actions against external security tools. When an agent proposes an action (e.g., "isolate this host", "disable this user", "post to Slack"), the execution engine routes it to the correct `ActionIntegration` implementation via the registry. Each integration encapsulates one external system: CrowdStrike for endpoint containment, Entra ID for identity response, Slack for notifications, and a generic webhook for any other HTTP-based target.

This is the **ports and adapters** pattern — same as `EnrichmentProviderBase`. The service layer (`execute_response_action_task`) calls `get_integration_for_action(action_subtype)` and then `integration.execute(action)`. It never imports a concrete class directly.

## Architecture

```
execute_response_action_task (worker task)
    ↓ calls
get_integration_for_action(action_subtype)    ← registry lookup
    ↓ returns
ActionIntegration (ABC, the port)
    ├── NullActionIntegration                 ← no-op fallback
    ├── GenericWebhookIntegration             ← HTTP POST to configurable URL
    ├── SlackActionIntegration                ← chat.postMessage, conversations.create
    ├── SlackUserValidationIntegration        ← DM + template rendering (needs DB)
    ├── CrowdStrikeIntegration                ← Falcon containment API
    └── EntraIDActionIntegration              ← Microsoft Graph identity actions
```

## Interfaces

### `ExecutionResult`

```python
@dataclass
class ExecutionResult:
    success: bool
    message: str
    data: dict[str, Any]       # arbitrary metadata for audit log
    rollback_supported: bool   # True if rollback() can reverse this action

    @classmethod
    def ok(cls, message, data=None) -> ExecutionResult: ...
    @classmethod
    def fail(cls, message, data=None) -> ExecutionResult: ...
```

### `ActionIntegration` (ABC)

```python
class ActionIntegration(ABC):
    default_approval_mode: str        # "always" | "never" | "agent_only"
    bypass_confidence_override: bool  # True = ignore confidence, always use base mode

    async def execute(self, action: AgentAction) -> ExecutionResult: ...   # ABSTRACT
    async def rollback(self, action: AgentAction) -> ExecutionResult: ...  # optional
    def supported_actions(self) -> list[str]: ...                          # ABSTRACT
    def is_configured(self) -> bool: ...                                   # default True
```

**Critical contract:** `execute()` and `rollback()` MUST NEVER RAISE. All errors are caught inside the method and returned as `ExecutionResult.fail(...)`. The task worker relies on this for safe parallel execution.

### `AgentAction` fields used by integrations

| Field | Type | Usage |
|-------|------|-------|
| `uuid` | UUID | Included in all log events and result data |
| `action_type` | str | e.g. `"containment"`, `"notification"` |
| `action_subtype` | str | e.g. `"isolate_host"`, `"send_alert"` |
| `payload` | dict | Integration-specific parameters (see each class docstring) |
| `confidence` | Decimal | Used by `resolve_approval_mode_for_action()` |

### Registry

```python
from app.integrations.actions.registry import get_integration_for_action

integration = get_integration_for_action(action_subtype)    # → ActionIntegration
result = await integration.execute(action)
```

The registry is a module-level singleton (`_REGISTRY`) built once at first call. Integrations that are not configured (no credentials) are skipped — their subtypes are not registered, so unhandled subtypes fall back to `NullActionIntegration`.

**For `SlackUserValidationIntegration`**: construct directly when you have a DB session:

```python
from app.integrations.actions.slack_user_validation import SlackUserValidationIntegration

integration = SlackUserValidationIntegration(db=session)
result = await integration.execute(action)
```

### Approval Mode Resolution

```python
from app.integrations.actions.base import resolve_approval_mode_for_action

effective_mode = resolve_approval_mode_for_action(
    action_type="containment",
    confidence=0.92,
    base_approval_mode="always",
    bypass_confidence_override=False,
)
# → "quick_review"  (confidence 0.85-0.95 threshold)
```

Confidence thresholds (from PRD):

| Confidence | Effective mode |
|------------|----------------|
| >= 0.95    | auto_approve   |
| >= 0.85    | quick_review   |
| >= 0.70    | human_review   |
| < 0.70     | block          |

If `bypass_confidence_override=True` (e.g. `EntraIDActionIntegration`), confidence is ignored and `base_approval_mode` is always used. This is a deliberate safety constraint for account-level actions.

### `ACTION_TYPE_DEFAULT_APPROVAL_MODE`

Lookup table for action-type-level defaults:

```python
ACTION_TYPE_DEFAULT_APPROVAL_MODE = {
    "containment": "always",
    "remediation": "always",
    "notification": "never",
    "escalation": "never",
    "enrichment": "never",
    "investigation": "never",
    "user_validation": "never",
    "custom": "always",
}
```

## Key Design Decisions

1. **Same ports-and-adapters pattern as enrichment.** The service layer is decoupled from every concrete integration. `get_integration_for_action()` is the single lookup point. New integrations require zero changes to the service or task worker.

2. **Module-level registry cache.** `_REGISTRY` is built once. Integrations that fail `is_configured()` are not registered — their subtypes silently fall back to `NullActionIntegration`. No startup failure for unconfigured integrations.

3. **Never raise from `execute()`.** The task worker calls `asyncio.gather()` across multiple actions. A raised exception would cancel sibling tasks. Every error path returns `ExecutionResult.fail(...)`.

4. **`bypass_confidence_override` for high-stakes integrations.** `EntraIDActionIntegration` sets this to `True`: disabling a user account always requires human approval, regardless of how confident the agent is. CrowdStrike sets `default_approval_mode="always"` but leaves `bypass_confidence_override=False` so high-confidence containment can be auto-approved.

5. **SSRF protection in `GenericWebhookIntegration`.** The webhook URL comes from `action.payload` at runtime. `validate_outbound_url()` is called before any HTTP request is made, blocking private/loopback/metadata addresses.

6. **`SlackUserValidationIntegration` is stateful.** It needs a DB session to load templates. It cannot be cached in the module-level registry. Always construct it directly from the task worker when `action_subtype == "validate_user_activity"` and a DB session is available.

7. **Rollback support is explicit.** `rollback_supported=True` in `ExecutionResult.data` signals to the audit log that a reverse action is available. `CrowdStrikeIntegration.rollback()` lifts containment; `EntraIDActionIntegration.rollback()` re-enables the user.

## Extension Pattern: Adding a New Integration

**Step 1:** Create `app/integrations/actions/my_tool_integration.py`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

class MyToolIntegration(ActionIntegration):
    default_approval_mode = "always"   # or "never" for notifications
    bypass_confidence_override = False

    def __init__(self, api_key: str | None = None) -> None:
        from app.config import settings
        self._api_key = api_key or settings.MY_TOOL_API_KEY or None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def execute(self, action: AgentAction) -> ExecutionResult:
        try:
            # ... your implementation
            return ExecutionResult.ok("Done", {"action_id": str(action.uuid)})
        except Exception as exc:
            return ExecutionResult.fail(str(exc), {"action_id": str(action.uuid)})

    def supported_actions(self) -> list[str]:
        return ["my_subtype_1", "my_subtype_2"]
```

**Step 2:** Add `MY_TOOL_API_KEY: str = ""` to `app/config.py` `Settings`.

**Step 3:** Register in `app/integrations/actions/registry.py` `_build_registry()`:

```python
from app.integrations.actions.my_tool_integration import MyToolIntegration

my_tool = MyToolIntegration()
if my_tool.is_configured():
    for subtype in my_tool.supported_actions():
        registry[subtype] = my_tool
    logger.info("action_integration_registered", integration="my_tool")
```

**Step 4:** Write `docs/integrations/my-tool/SETUP.md` (required permissions, credential steps).

**Step 5:** Add tests in `tests/test_action_integrations.py`.

That's all. The service layer, task worker, and approval gate require zero changes.

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---------|-------|-----------|
| All actions go to `NullActionIntegration` | Integration not configured | Check `is_configured()` — verify env vars are set |
| CrowdStrike returns "Failed to obtain OAuth2 token" | Invalid client credentials | Check `CROWDSTRIKE_CLIENT_ID`/`SECRET`; verify API client has Containment scope |
| Entra ID "failed to obtain access token" | Missing or invalid `ENTRA_*` vars | Verify tenant ID, client ID, secret; check `User.ReadWrite.All` permission in Azure |
| Entra ID `force_mfa` deletes 0 methods | No MFA methods registered or all are password | Normal — user has no TOTP/phone methods to delete |
| Slack "channel_not_found" | Bot not invited to channel | `/invite @CalsetaBot` in the target channel |
| Slack "not_authed" | Invalid `SLACK_BOT_TOKEN` | Regenerate token in Slack app config |
| `SlackUserValidationIntegration` returns "template not found" | Template name in payload doesn't match any DB row | Check `user_validation_templates.name`; verify migration ran |
| Webhook SSRF blocked | `action.payload.url` resolves to a private IP | Use `SSRF_ALLOWED_HOSTS` in dev only; fix the target URL in prod |
| Registry not picking up new integration | Module not imported in `registry.py` | Add import and registration block to `_build_registry()` |

## File Map

| File | Purpose |
|------|---------|
| `base.py` | `ActionIntegration` ABC, `ExecutionResult`, approval mode resolution |
| `registry.py` | `get_integration_for_action()` — subtype → integration lookup |
| `null_integration.py` | No-op fallback for unregistered subtypes |
| `generic_webhook.py` | HTTP POST to configurable URL (SSRF-protected) |
| `slack_integration.py` | Slack notifications, channel creation |
| `slack_user_validation.py` | Slack DM + template rendering (DB-dependent) |
| `crowdstrike_integration.py` | Falcon endpoint containment / lift |
| `entra_id_integration.py` | Microsoft Graph identity actions |

## Test Coverage

| Test file | What to test |
|-----------|-------------|
| `tests/test_action_integrations.py` | Unit tests for each integration with mocked httpx |
| `tests/test_action_registry.py` | Registry build, fallback to null, is_configured paths |
| `tests/test_action_service.py` | End-to-end: action proposed → approved → executed → result stored |

Key scenarios to cover:
- `execute()` never raises — mock httpx to raise `RequestError`; verify `ExecutionResult.fail`
- SSRF blocked URL in `GenericWebhookIntegration`
- `CrowdStrikeIntegration.rollback()` lifts containment
- `EntraIDActionIntegration` returns fail when `is_configured()` is False
- `SlackUserValidationIntegration` renders template body with `{{alert.title}}` substitution
- Registry falls back to `NullActionIntegration` for unknown subtypes
