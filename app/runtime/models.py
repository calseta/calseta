"""Runtime data classes — shared between engine, prompt builder, and supervisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RuntimeContext:
    agent_id: int                     # agent_registrations.id
    task_key: str                     # "alert:{id}", "issue:{id}", "routine:{id}"
    heartbeat_run_id: int             # heartbeat_runs.id — for cost attribution
    alert_id: int | None = None       # alerts.id if this is alert work
    assignment_id: int | None = None  # alert_assignments.id if alert work
    run_uuid: UUID | None = None      # heartbeat_runs.uuid — for log store paths


@dataclass
class RuntimeResult:
    success: bool
    findings: list[dict] = field(default_factory=list)
    actions_proposed: list[dict] = field(default_factory=list)
    total_cost_cents: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    session_id: str | None = None   # ClaudeCodeAdapter session continuity
    error: str | None = None


@dataclass
class BuiltPrompt:
    system_prompt: str             # Assembled layers 1+2+6
    messages: list[dict]           # Conversation history (for session resume)
    layer_tokens: dict[str, int]   # Estimated tokens per layer
    total_tokens_estimated: int
    kb_pages_excluded: list[str] = field(default_factory=list)


@dataclass
class SupervisionReport:
    checked: int = 0
    timed_out: int = 0
    budget_stopped: int = 0
    errors: list[str] = field(default_factory=list)
