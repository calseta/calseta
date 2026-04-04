# Part 2: Actions & Multi-Agent Orchestration

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 2: Actions & Multi-Agent Orchestration

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 2, Phase 3, Phase 5

---

### Data Model

#### `agent_actions`

Actions proposed or executed by agents. Leverages Calseta's **existing approval system** (`WorkflowApprovalRequest`, pluggable notifiers, Procrastinate task queue) rather than building a parallel approval flow.


| Column                  | Type        | Notes                                                                                                                  |
| ----------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                                                                     |
| `alert_id`              | uuid        | FK `alerts.id`, NOT NULL                                                                                               |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                                                                                  |
| `assignment_id`         | uuid        | FK `alert_assignments.id`, NOT NULL                                                                                    |
| `action_type`           | enum        | `containment`, `remediation`, `notification`, `escalation`, `enrichment`, `investigation`, `user_validation`, `custom` |
| `action_subtype`        | text        | NOT NULL — specific action ("block_ip", "disable_user", "isolate_host", "send_slack", "create_ticket")                 |
| `status`                | enum        | `proposed`, `approved`, `rejected`, `executing`, `completed`, `failed`, `cancelled`                                    |
| `payload`               | jsonb       | NOT NULL — action parameters (IP to block, user to disable, message to send, etc.)                                     |
| `confidence`            | numeric(3,2)| NULL — agent's confidence in this action (0.00–1.00); used for auto-approval threshold checks                          |
| `approval_request_id`   | int         | NULL — FK `workflow_approval_requests.id`, set when approval is required                                               |
| `execution_result`      | jsonb       | NULL — result from integration execution                                                                               |
| `executed_at`           | timestamptz | NULL                                                                                                                   |
| `created_at`            | timestamptz | NOT NULL                                                                                                               |


> Cross-ref: `assignment_id` references `alert_assignments` from [Part 1].

**How this integrates with the existing approval system:**

Calseta already has a production-ready approval gate with:

- `WorkflowApprovalRequest` model (status lifecycle: `pending → approved/rejected/expired`)
- Pluggable notifier system (`SlackApprovalNotifier` with interactive buttons, `TeamsApprovalNotifier`, `NullApprovalNotifier`)
- Browser-based approval page (token-authenticated, no API key needed)
- Async execution via Procrastinate task queue (returns 202, executes in background)
- Confidence scores, risk levels, responder tracking, activity audit trail
- Per-workflow approval modes: `always`, `agent_only`, `never`

**Rather than duplicating this, the control plane extends it:**

1. When an agent proposes an action, the system creates an `agent_actions` row AND a `WorkflowApprovalRequest` (if approval is needed based on the workflow's `approval_mode`)
2. The existing notifier system (Slack buttons, Teams cards, browser page) handles the human review UX — no new notification code needed
3. The existing `process_approval_decision()` function handles approve/reject, then triggers execution of the response action via a new Procrastinate task (`execute_response_action_task`)
4. The existing activity event system logs all decisions automatically

**Changes needed to the existing approval system:**

- Extend `WorkflowApprovalRequest.trigger_context` to store response action metadata (action_type, action_subtype, payload, agent_id, assignment_id)
- Add a new `trigger_type` value: `"agent_action"` (alongside existing `"agent"`, `"human"`)
- Add a new Procrastinate task `execute_response_action_task` that runs the `ActionIntegration` after approval (parallel to existing `execute_approved_workflow_task`)
- Extend notifier message templates to show response action details (what action, against what target, agent confidence/reasoning)
- Add `action_type`-based approval mode logic: containment/remediation default to `always`, notification/escalation/enrichment/investigation default to `never`

**Status state machine:**

```
proposed → pending_approval (approval required, WorkflowApprovalRequest created)
proposed → executing (no approval required, auto-execute)
pending_approval → approved → executing (human approves via existing Slack/Teams/browser flow)
pending_approval → rejected (human rejects)
pending_approval → expired (approval timeout, existing expiry-on-read logic)
executing → completed (integration returns success)
executing → failed (integration returns error)
proposed → cancelled (agent or operator cancels)
```

#### Approval Policy Defaults by Action Type

The existing per-workflow `approval_mode` field (`always`/`agent_only`/`never`) handles most cases. For finer-grained control over response actions, we extend the workflow model or add a lightweight config:


| Action Type       | Default Approval Mode | Rationale                                                                 |
| ----------------- | --------------------- | ------------------------------------------------------------------------- |
| `containment`     | `always`              | Blocking IPs, isolating hosts = high-impact                               |
| `remediation`     | `always`              | Disabling users, revoking sessions = high-impact                          |
| `notification`    | `never`               | Sending Slack messages, creating tickets = low-risk                       |
| `escalation`      | `never`               | Routing to human = inherently safe                                        |
| `enrichment`      | `never`               | Additional lookups = low-risk                                             |
| `investigation`   | `never`               | Reading logs, querying SIEMs = low-risk                                   |
| `user_validation` | `never`               | Outbound Slack DM to user for activity confirmation = low-risk, automated |


#### Confidence-Scored Auto-Approval (Override Layer)

> **Can you require approval regardless of confidence score?** Yes. Set `bypass_confidence_override: true` in the `ActionIntegration` config. When this flag is set, the confidence override table below is ignored — the action always follows `approval_mode` exactly. This is the recommended setting for `disable_user`, `revoke_sessions`, and any action with irreversible consequences. Stored as a field in the integration's config JSONB on `agent_tools`.

When `approval_mode` resolves to `always` or `agent_only`, the agent's `confidence` score on the proposed action can further refine the approval routing **unless `bypass_confidence_override: true` is set**. This is an **opt-in override layer** — it only applies to integrations where speed is preferred over review (e.g., `block_ip` during an active intrusion).


| Confidence Range | Approval Behavior                                                                            | Rationale                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `0.95–1.00`      | **Auto-approve** — execute immediately, log as auto-approved                                 | Critical threat confirmed (ransomware, active C2). Speed matters more than review.                                    |
| `0.85–0.94`      | **Quick review** — notify operator, 15-minute approval window, auto-approve on expiry        | High confidence (confirmed malware, impossible travel). Operator can override within window.                          |
| `0.70–0.84`      | **Human approval required** — standard approval flow via Slack/Teams/browser                 | Moderate confidence (suspicious but not confirmed). Human judgment needed.                                            |
| `< 0.70`         | **Block auto-execution** — action stays `proposed`, agent instructed to gather more evidence | Insufficient evidence. Forcing the agent to investigate further prevents false positives from triggering containment. |


> [!note] Confidence thresholds are configurable
> The thresholds above are defaults. Operators can adjust per-action-type or per-integration via config (e.g., "never auto-approve `disable_user` regardless of confidence" or "lower the quick-review threshold to 0.80 for `block_ip`"). This is stored as optional `confidence_thresholds` JSONB on `ActionIntegration` config — not a separate table.

> [!note] Implementation Note
> The simplest approach: each `ActionIntegration` declares its default `approval_mode` and optional `confidence_thresholds`. Operators can override per-integration via config. This avoids a separate `approval_policies` table — the existing workflow approval infrastructure handles everything. The confidence override is evaluated in the action proposal handler before creating a `WorkflowApprovalRequest`.

#### `agent_invocations`

Tracks parent→child agent delegation. When an orchestrator invokes a specialist sub-agent, this records the full lifecycle.


| Column             | Type        | Notes                                                                |
| ------------------ | ----------- | -------------------------------------------------------------------- |
| `id`               | uuid        | PK                                                                   |
| `parent_agent_id`  | int         | FK `agent_registrations.id`, NOT NULL — the orchestrator             |
| `child_agent_id`   | int         | FK `agent_registrations.id`, NOT NULL — the specialist               |
| `alert_id`         | uuid        | FK `alerts.id`, NOT NULL                                             |
| `assignment_id`    | uuid        | FK `alert_assignments.id`, NOT NULL                                  |
| `task_description` | text        | NOT NULL — what the orchestrator asked for                           |
| `input_context`    | jsonb       | NOT NULL — structured input passed to sub-agent                      |
| `output_result`    | jsonb       | NULL — sub-agent's findings (populated on completion)                |
| `status`           | enum        | `queued`, `running`, `completed`, `failed`, `timed_out`, `cancelled` |
| `cost_cents`       | int         | NOT NULL, default 0 — rolled up from sub-agent's cost_events         |
| `started_at`       | timestamptz | NULL                                                                 |
| `completed_at`     | timestamptz | NULL                                                                 |
| `created_at`       | timestamptz | NOT NULL                                                             |


**Constraints:**

- `parent_agent_id` must be an `orchestrator` type agent
- `child_agent_id` must be in the parent's `sub_agent_ids` array
- Depth is limited to 1 level in initial implementation (orchestrator → specialist only, no sub-sub-agents)

#### Required Indexes (Part 2)

```sql
CREATE INDEX idx_agent_actions_status ON agent_actions(status);
CREATE INDEX idx_agent_actions_assignment ON agent_actions(assignment_id);
CREATE INDEX idx_agent_actions_approval ON agent_actions(approval_request_id) WHERE approval_request_id IS NOT NULL;
CREATE INDEX idx_agent_invocations_parent ON agent_invocations(parent_agent_id, alert_id);
CREATE INDEX idx_agent_invocations_child ON agent_invocations(child_agent_id, status);
CREATE INDEX idx_agent_invocations_assignment ON agent_invocations(assignment_id);
CREATE INDEX idx_cost_events_invocation ON cost_events(invocation_id) WHERE invocation_id IS NOT NULL;
```

---

### Integration Execution Engine

> [!important] Relationship to Existing Workflows
> Calseta v1 already has a workflow execution engine — Python HTTP automation scripts (`async def run(ctx: WorkflowContext) -> WorkflowResult`). The Integration Execution Engine **is** the workflow engine, extended with action-specific conventions. This means:
>
> 1. **Action integrations are workflows** registered with `category: "integration"` in the tool registry
> 2. The **generic webhook integration** is the simplest case: a workflow that does `ctx.http.post(url, payload)` — operators configure the URL and payload template
> 3. Adding a new integration = writing a new workflow (same pattern operators already know from v1)
> 4. Existing approval gate (`WorkflowApprovalRequest`) already handles the human-in-the-loop step
>
> The `ActionIntegration` ABC below defines the interface that integration workflows must satisfy. Implementors subclass it like `EnrichmentProviderBase` — the same ports-and-adapters pattern used everywhere in Calseta.
>
> **Extending integrations:** An LLM context file `app/integrations/actions/CONTEXT.md` documents how to add new integrations: subclass `ActionIntegration`, implement `execute()` + `rollback()` + `supported_actions()`, register in the tool registry, write the `documentation` field with setup steps and least-privilege permissions, add `docs/integrations/{name}/SETUP.md`.

When an approved action needs to execute (block IP, disable user, etc.), Calseta executes via the extended workflow engine.

#### Integration Interface

```python
class ActionIntegration(ABC):
    """
    Base class for action execution integrations.
    Same pattern as EnrichmentProviderBase — ports and adapters.
    
    Paperclip ref: The equivalent in Paperclip is the adapter pattern in
    /packages/adapters/ — each adapter implements a common interface.
    In Calseta this maps to ActionIntegration subclasses.
    """

    @abstractmethod
    async def execute(self, action: AgentAction) -> ExecutionResult:
        """Execute the approved action."""
        ...

    @abstractmethod
    async def rollback(self, action: AgentAction) -> ExecutionResult:
        """Reverse the action if possible."""
        ...

    @abstractmethod
    def supported_actions(self) -> list[str]:
        """Return list of action_subtypes this integration handles."""
        ...
```

#### Initial Integrations (Phase 3)


| Integration        | Actions                                                                   | Target                         |
| ------------------ | ------------------------------------------------------------------------- | ------------------------------ |
| CrowdStrike Falcon | `isolate_host`, `lift_containment`                                        | Endpoint isolation             |
| Microsoft Entra ID | `disable_user`, `revoke_sessions`, `force_mfa`                            | Identity response              |
| Palo Alto Networks | `block_ip`, `block_domain`, `block_url`                                   | Network containment            |
| Slack              | `send_alert`, `create_channel`, `notify_oncall`, `validate_user_activity` | Notification + User Validation |
| Jira / ServiceNow  | `create_ticket`, `update_ticket`                                          | Ticketing                      |
| Generic Webhook    | `webhook_post`                                                            | Custom integrations            |


> Cross-ref: Integration credentials use the secrets system in [Part 5: Platform Operations].

#### User Validation via Slack DM (Decentralized Alert Triage)

A key action type for reducing alert fatigue: **automated user validation**. When an alert involves user activity that may be legitimate, the system can automatically DM the affected user to confirm or deny. This is triggered by **User Validation Rules** — operator-defined automation rules that match on alert conditions and define the exact validation flow (message template, buttons vs. free text, timeout, escalation behavior).

##### User Validation Rules

Operators define rules that say: "when this type of alert arrives, automatically run this validation flow." Rules are stored in a new `user_validation_rules` table:

| Column                  | Type        | Notes                                                                                                         |
| ----------------------- | ----------- | ------------------------------------------------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                                                            |
| `name`                  | text        | NOT NULL — "Password Change Confirmation", "New Device Login"                                                 |
| `description`           | text        | NULL                                                                                                          |
| `is_active`             | boolean     | NOT NULL, default true                                                                                        |
| `trigger_conditions`    | jsonb       | NOT NULL — same targeting syntax as context documents and alert routing. Examples: `{"alert_title_contains": "password changed"}`, `{"detection_rule_ids": ["uuid"]}`, `{"severity": ["high", "critical"], "tags": ["identity"]}` |
| `template_id`           | uuid        | FK `user_validation_templates.id`, NOT NULL                                                                   |
| `user_field_path`       | text        | NOT NULL — dot-notation path in alert payload to the user identifier (e.g., `"normalized.user_email"`, `"raw_payload.user.upn"`) |
| `timeout_hours`         | int         | NOT NULL, default 4                                                                                           |
| `on_confirm`            | enum        | `close_alert`, `add_finding`, `nothing` — default `close_alert`                                               |
| `on_deny`               | enum        | `escalate_alert`, `bump_severity`, `create_issue`, `nothing` — default `escalate_alert`                       |
| `on_timeout`            | enum        | `escalate_alert`, `create_issue`, `nothing` — default `escalate_alert`                                        |
| `priority`              | int         | NOT NULL, default 0 — evaluation order when multiple rules match                                              |
| `created_at`            | timestamptz | NOT NULL                                                                                                      |
| `updated_at`            | timestamptz | NOT NULL                                                                                                      |

**User Validation Templates** (`user_validation_templates` table) define the exact message sent and the response mechanism:

| Column          | Type   | Notes                                                                                                                               |
| --------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `id`            | uuid   | PK                                                                                                                                  |
| `name`          | text   | NOT NULL — "Activity Confirmation (Buttons)", "Security Incident Report (Free Text)"                                               |
| `message_body`  | text   | NOT NULL — Slack Block Kit JSON template. Supports `{{alert.title}}`, `{{alert.occurred_at}}`, `{{user.email}}` Mustache variables. |
| `response_type` | enum   | `buttons` (Yes/No interactive buttons), `text` (free-text reply via Slack DM reply)                                                 |
| `confirm_label` | text        | NULL — button label for confirmation. Default: "Yes, that was me"                                                                   |
| `deny_label`    | text        | NULL — button label for denial. Default: "No, that wasn't me"                                                                       |
| `created_at`    | timestamptz | NOT NULL                                                                                                                             |
| `updated_at`    | timestamptz | NOT NULL                                                                                                                             |

**Built-in templates (seeded at startup):**

| Template                           | Response Type | Use case                                              |
| ---------------------------------- | ------------- | ----------------------------------------------------- |
| `activity_confirmation_buttons`    | buttons       | "Was this you?" Yes/No for any activity               |
| `new_device_login_buttons`         | buttons       | "Did you sign in from a new device?"                  |
| `password_change_buttons`          | buttons       | "Did you change your password?"                       |
| `suspicious_activity_report`       | text          | "Please describe what you were doing at this time"    |
| `mfa_change_buttons`               | buttons       | "Did you modify your MFA settings?"                   |

**Standard use cases and trigger conditions:**

| Use Case | Trigger condition example | Template |
| --- | --- | --- |
| Impossible travel | `alert_title_contains: "impossible travel"` | `activity_confirmation_buttons` |
| New device login | `detection_rule_name_contains: "new device"` | `new_device_login_buttons` |
| Password/MFA reset | `alert_title_contains: "password changed"` OR `"MFA reset"` | `password_change_buttons` or `mfa_change_buttons` |
| OAuth app consent | `tags_contains: "oauth"` | `activity_confirmation_buttons` |
| Credential stuffing (batch) | `alert_title_contains: "credential stuffing"` | Campaign flow (Phase 8+) |

**Execution flow:**

```
Alert arrives and passes enrichment
  │
  ├─ User Validation Rule engine evaluates active rules against alert
  │   (same deterministic targeting as alert routing — zero LLM tokens)
  │
  ├─ Rule matches → resolves user identifier from user_field_path
  │   → looks up Slack user ID via Slack directory (Entra/Okta lookup fallback)
  │
  ├─ SlackUserValidationIntegration executes template:
  │   → Renders Block Kit message with alert context variables
  │   → DMs user with configured response type (buttons or text input)
  │   → Records delivery in per-recipient tracking table
  │
  ├─ User responds:
  │   ├─ Confirms → on_confirm action executes (close_alert, add_finding, etc.)
  │   └─ Denies  → on_deny action executes (escalate_alert, bump_severity, etc.)
  │
  └─ Timeout (timeout_hours) → on_timeout action executes
```

**Rule evaluation:** Runs as part of the enrichment completion pipeline — after enrichment, before agent dispatch. Zero LLM tokens. Rules are evaluated deterministically, same as context document targeting and alert routing.

**API surface:**
```
POST   /api/v1/user-validation/rules              Create rule
GET    /api/v1/user-validation/rules              List rules
PATCH  /api/v1/user-validation/rules/{id}         Update rule
DELETE /api/v1/user-validation/rules/{id}         Delete rule
POST   /api/v1/user-validation/templates          Create template
GET    /api/v1/user-validation/templates          List templates
GET    /api/v1/user-validation/templates/{id}     Get template details
PATCH  /api/v1/user-validation/templates/{id}     Update template (fails if used in active campaign)
DELETE /api/v1/user-validation/templates/{id}     Delete template (fails if referenced by active rules)
GET    /api/v1/user-validation/recipients         List per-recipient validation history
```

**Implementation:** Extends the existing `SlackApprovalNotifier` pattern — same Slack app, same interactive button handling, different message template and callback behavior. The `SlackUserValidationIntegration` is an `ActionIntegration` that handles the `validate_user_activity` action subtype.

**Approval mode:** `user_validation` defaults to `never` (no operator approval needed to send a DM asking a user about their own activity). Operators can override to `always` if they want to review before outbound DMs are sent.

**User Validation Campaign System (Future — Phase 8+):**

> [!note] Naming disambiguation
> "User Validation Campaigns" (this section) = bulk Slack DM outreach for mass validation scenarios.
> "Investigation Campaigns" (Part 4) = strategic objective containers tracking metrics like MTTD reduction.
> These are completely different features that share the word "campaign."

For batch user validation (e.g., after a credential stuffing attack affecting 50 users), extend the `user_validation` action into a **User Validation Campaign system**:

1. Operator or agent creates a campaign → selects pre-approved template, audience (list of users or alert-derived list), schedule
2. **Approval gate** → campaign posts summary to ops channel for review before any DMs are sent (required when recipient count exceeds guardrail threshold)
3. Batched delivery → DMs queued to Procrastinate task queue and sent in rate-limited batches; each recipient tracked individually with Slack message timestamp
4. Tracking → per-recipient status (sent/failed/acknowledged/denied), aggregate dashboard (X% confirmed, Y% denied, Z% no response)
5. Auto-triage → confirmed responses auto-close associated alerts; denied responses auto-escalate

**Campaign guardrails** (all settings are DB-driven, surfaced in the settings UI at `/control-plane/settings/user-validation`, changeable at runtime without restart):

| Guardrail | Default | Description |
| --- | --- | --- |
| `max_messages_per_recipient_per_day` | 3 | Prevents alert fatigue for individual users |
| `approval_required_above_recipients` | 50 | Campaigns with > N recipients require operator approval before sending |
| `rate_limit_per_minute` | 10 | Max DMs sent per minute (Slack rate limit buffer) |
| `opt_out_enabled` | true | Users can reply "STOP" to opt out; opt-out stored per user, respected by all future campaigns |
| `opt_out_ttl_days` | 30 | Opt-out expires after N days; NULL = permanent |
| `require_template_approval` | false | If true, new templates require operator approval before use in campaigns |

These guardrail settings are stored in a `platform_settings` JSONB-backed settings table (see Platform Settings section in Part 5), not hardcoded. All settings with security implications are DB-driven so they can be changed without a deployment.

This treats user validation like a mini messaging campaign system but native to Slack. Built on the same `ActionIntegration` infrastructure — the campaign is just N parallel `validate_user_activity` actions with shared tracking metadata.

> Cross-ref: Investigation campaigns (strategic objectives for metric tracking) are in [Part 4: Operational Management].

---

### Multi-Agent Orchestration

The core pattern: **Calseta routes alerts to orchestrators deterministically, then orchestrators drive specialist sub-agents dynamically.**

#### Agent Types


| Type             | Purpose                                                                                                                    | Examples                                                               |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Orchestrator** | Receives alerts, decides investigation strategy, delegates to specialists, synthesizes findings, proposes response actions | Lead Investigator, Credential Theft Investigator, Malware Investigator |
| **Specialist**   | Performs focused investigation tasks on demand from orchestrators, returns structured findings                             | SIEM Query Agent, Identity Agent, Endpoint Agent, Threat Intel Agent   |


#### Alert Routing (Deterministic)

Calseta matches incoming alerts to orchestrators based on `alert_filter` rules — the same targeting rule syntax used by context documents. No LLM tokens burned on routing.

```
Alert arrives (enriched) → match against orchestrator alert_filters (by priority)
  → First match wins → alert queued for that orchestrator
  → No match → alert goes to default orchestrator (if configured) or manual queue
```

Multiple orchestrators can exist for different alert types:

- "Credential Theft Investigator" handles `credential_access`, `initial_access` alerts
- "Malware Investigator" handles `execution`, `persistence`, `defense_evasion` alerts
- "General Investigator" handles everything else (low priority, catches unmatched)

#### Investigation Flow (Dynamic, Wave-Structured)

Once an orchestrator checks out an alert, it drives the investigation using LLM reasoning. Investigations follow a **wave structure** — parallel specialist execution within each wave, with deterministic checkpoint evaluation between waves. The wave convention is expressed in the orchestrator's `methodology` field (markdown), not as rigid schema. The runtime engine enforces checkpoint rules at wave boundaries.

```
Wave 1 — Context Gathering (parallel):
  ├─ Identity Agent: user profile + recent activity
  ├─ SIEM Agent: related events in time window
  └─ Threat Intel Agent: deep IOC analysis
  └── CHECKPOINT: At least 2/3 specialists must return findings.
      If all return empty, flag as potential false positive.

Wave 2 — Scope Assessment (parallel, conditional):
  ├─ Endpoint Agent: process trees on affected hosts (if Wave 1 found lateral movement)
  ├─ SIEM Agent (follow-up): expanded entity search based on Wave 1 findings
  └─ Historical Context Agent: prior investigations involving same entities
  └── CHECKPOINT: If scope is expanding (new hosts/users discovered),
      inject escalation context before Wave 3.

Wave 3 — Response:
  ├─ Orchestrator synthesizes all findings → confidence + verdict
  ├─ Orchestrator proposes response actions
  └── CHECKPOINT: Approval gate (existing system) for containment/remediation.
```

**How waves work in practice:**

The orchestrator LLM decides the investigation flow — waves are a **methodology convention**, not a rigid execution engine. The `methodology` field on `agent_registrations` documents the expected wave structure in markdown. The runtime engine adds two deterministic behaviors:

1. **Wait-for-parallel**: When an orchestrator issues `delegate_parallel`, the runtime waits for all invocations to complete (or timeout) before returning results to the orchestrator. This is already the natural behavior of `delegate_parallel`.
2. **Checkpoint injection**: At configurable points (after parallel results return), the runtime can inject checkpoint context into the orchestrator's next prompt: "Budget status: $0.23 of $1.00 spent. Stall status: 0 empty results. Time: 2m of 10m elapsed." This gives the orchestrator situational awareness without requiring a separate governance agent.

The full step-by-step flow:

```
1. Orchestrator receives: enriched alert + sub-agent catalog (capabilities + descriptions)
2. Orchestrator reasons (LLM): "Based on this alert, I need to check X, Y, Z"
3. Orchestrator delegates: invoke specialists in parallel via MCP tools / REST API (Wave 1)
4. Specialists execute: each runs its focused task, returns structured JSON findings
5. Runtime injects checkpoint context: budget/stall/time status + severity flags
6. Orchestrator collects results, may delegate follow-up tasks based on findings (Wave 2)
7. Orchestrator synthesizes: produce overall finding + confidence + recommended actions
8. Orchestrator proposes response actions → existing approval system (Wave 3)
```

The orchestrator can adapt mid-investigation. If the SIEM agent finds lateral movement, the orchestrator can invoke the endpoint agent for additional hosts that weren't in the original alert. This is where LLM intelligence adds value — rigid workflows can't do this.

#### Investigation Checkpoints (Deterministic Guardrails)

While the orchestrator drives investigation dynamically via LLM reasoning, **deterministic checkpoints** prevent drift, runaway costs, and stuck investigations. These are enforced by the runtime engine — no LLM tokens burned on checkpoint evaluation.


| Checkpoint              | Trigger                                                                                        | Action                                                                                                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Budget**              | Investigation cost exceeds `max_cost_per_alert_cents`                                          | Pause investigation, notify operator, surface cost breakdown. Operator can raise limit and resume or force-close.                                                   |
| **Depth**               | Sub-agent invocation count exceeds `max_sub_agent_calls`                                       | Pause investigation, force orchestrator to synthesize with available findings or escalate.                                                                          |
| **Stalling**            | `stall_threshold` consecutive sub-agent invocations return no actionable findings              | Flag investigation as stalling, notify operator. Orchestrator receives "investigation stalling — synthesize or escalate" injection before next LLM call.            |
| **Time**                | Investigation duration exceeds `max_investigation_minutes`                                     | Force resolution or escalation. Same cancel flow as agent timeout.                                                                                                  |
| **Severity Escalation** | Any specialist returns finding with `malice: Malicious` or detects lateral movement indicators | Runtime injects "re-evaluate priority and consider immediate escalation" prompt into orchestrator context before continuing. Does not pause — adds urgency context. |


> [!important] Checkpoints are deterministic, not governance agents
> These guardrails are platform-level controls evaluated by the runtime engine — not separate "governance agents" that burn tokens re-reading investigation context. This honors Calseta's core principle: deterministic operations stay deterministic. The orchestrator IS the governance layer for investigation quality; the platform provides the safety rails.

#### Capability Declarations

Specialists declare structured capabilities so orchestrators know what's available:

```json
{
  "capabilities": [
    {
      "name": "search_events",
      "description": "Run queries against SIEM to find related events within a time window",
      "input_schema": {
        "query": {"type": "string", "description": "KQL or SPL query"},
        "timerange_hours": {"type": "integer", "default": 24}
      },
      "output_schema": {
        "events": {"type": "array"},
        "count": {"type": "integer"},
        "query_executed": {"type": "string"}
      }
    },
    {
      "name": "build_timeline",
      "description": "Build chronological timeline of all activity for an entity",
      "input_schema": {
        "entity": {"type": "string"},
        "entity_type": {"type": "string", "enum": ["user", "host", "ip", "domain"]}
      },
      "output_schema": {
        "timeline": {"type": "array"},
        "earliest": {"type": "string"},
        "latest": {"type": "string"}
      }
    }
  ]
}
```

The orchestrator's system prompt includes the full sub-agent catalog. This is how it knows who to call and what to ask for.

#### Cost Rollup

Sub-agent costs roll up through the invocation chain:

```
Alert Investigation #ALT-2026-0847: Total cost $0.47
├─ Lead Investigator (claude-opus): $0.12 (reasoning + synthesis)
├─ Identity Agent (claude-haiku): $0.04
├─ SIEM Query Agent (claude-haiku): $0.08
│   └─ Follow-up SIEM query: $0.03
├─ Threat Intel Agent (claude-sonnet): $0.11
└─ Response recommendation: $0.09
```

This visibility is critical — operators can see exactly where investigation budget goes and optimize (e.g., "the threat intel agent is expensive, can we use a cheaper model?").

#### Example: Full Investigation Trace

```
Alert: "Suspicious login from TOR exit node for jsmith@corp.com"
  │
  ├─ Calseta pipeline: ingest → normalize → enrich (VT, AbuseIPDB) → contextualize
  │
  ├─ Routing: matches "credential_access" + severity "high"
  │  → routed to "Credential Theft Investigator" orchestrator
  │
  ├─ Orchestrator checks out alert, receives:
  │   - Full enriched alert payload
  │   - Sub-agent catalog: [identity, siem, endpoint, threat-intel, historical]
  │
  ├─ Orchestrator delegates (parallel):
  │   ├─ Identity Agent: "Full user profile + recent activity for jsmith@corp.com"
  │   ├─ SIEM Agent: "Auth events for jsmith last 48h + any TOR-related events"
  │   └─ Threat Intel Agent: "Deep dive on 185.220.101.42 beyond basic enrichment"
  │
  ├─ Results return:
  │   ├─ Identity: "IT admin, MFA enabled, last normal login Chicago 3h ago"
  │   ├─ SIEM: "2 failed logins from TOR, 1 success. 3 new OAuth app consents post-auth."
  │   └─ Threat Intel: "Known TOR exit, linked to credential stuffing campaigns"
  │
  ├─ Orchestrator adapts — OAuth consents are suspicious, needs more info:
  │   └─ SIEM Agent (follow-up): "List all OAuth app consents by jsmith last 24h"
  │      └─ Result: 3 unfamiliar apps consented in 10-minute window
  │
  ├─ Orchestrator synthesizes:
  │   "Confirmed compromise. Impossible travel (Chicago → TOR). Post-auth OAuth
  │    consents = persistence attempt. High confidence true positive."
  │
  ├─ Orchestrator proposes response actions:
  │   ├─ disable_user (jsmith@corp.com)        → requires approval
  │   ├─ revoke_sessions (jsmith@corp.com)     → requires approval
  │   ├─ revoke_oauth_apps ([3 apps])          → requires approval
  │   ├─ create_ticket (P1 incident)           → auto-approved
  │   └─ notify_oncall (#security-incidents)   → auto-approved
  │
  ├─ Slack notification fires with full context
  │   Operator sees: alert details + all sub-agent findings + reasoning + proposed actions
  │
  └─ Operator approves containment → actions execute via integrations
```

---

---

