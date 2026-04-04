"""PromptBuilder — assembles the 6-layer prompt for a managed agent invocation.

Layer order:
  Layer 1: agent.system_prompt + per-agent instruction_files + global instruction_files
  Layer 2: agent.methodology (wrapped in <methodology> tags)
  Layer 3: KB context — stubbed in Phase 1 (empty)
  Layer 4: Alert/task context — assembled as the first user message
  Layer 5: Session state — injected into messages list
  Layer 6: Runtime checkpoint — appended to system prompt

Final structure:
  system_prompt = layer1 + "\n\n" + layer2 + "\n\n" + layer6
  messages = [layer4_user_msg, ...layer5_history...]
"""

from __future__ import annotations

import json

import structlog

if True:
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.db.models.agent_registration import AgentRegistration
        from app.db.models.agent_task_session import AgentTaskSession
        from app.runtime.models import BuiltPrompt, RuntimeContext

logger = structlog.get_logger(__name__)

# Rough estimate: 1 token ≈ 4 chars
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class PromptBuilder:
    """Assembles the 6-layer prompt for a managed agent invocation."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
        session: AgentTaskSession | None,
    ) -> BuiltPrompt:
        """Build the complete prompt structure for a managed agent invocation."""
        from app.runtime.models import BuiltPrompt

        layer1 = await self._build_layer1(agent)
        layer2 = self._build_layer2(agent)
        # Layer 3 is stubbed in Phase 1 — KB context populated in Phase 6
        layer3 = self._build_layer3_kb()  # noqa: F841  # KB CONTEXT STUB
        layer4_msg = await self._build_layer4_alert_context(context)
        layer6 = self._build_layer6_checkpoint(agent)

        # Assemble system prompt: layers 1 + 2 + 6
        system_parts = [layer1]
        if layer2:
            system_parts.append(layer2)
        system_parts.append(layer6)
        system_prompt = "\n\n".join(p for p in system_parts if p)

        # Assemble messages list from layer 4 + layer 5
        messages = self._build_messages(layer4_msg, session)

        # Token estimates per layer
        layer_tokens: dict[str, int] = {
            "layer1_system": _estimate_tokens(layer1),
            "layer2_methodology": _estimate_tokens(layer2),
            "layer3_kb": 0,  # stub
            "layer4_context": _estimate_tokens(layer4_msg) if layer4_msg else 0,
            "layer6_checkpoint": _estimate_tokens(layer6),
        }
        total_tokens_estimated = sum(layer_tokens.values())
        # Add existing session tokens if resuming
        if session and session.session_params.get("messages"):
            existing_msgs = session.session_params["messages"]
            for msg in existing_msgs:
                content = msg.get("content", "")
                if isinstance(content, str):
                    total_tokens_estimated += _estimate_tokens(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            total_tokens_estimated += _estimate_tokens(block["text"])

        return BuiltPrompt(
            system_prompt=system_prompt,
            messages=messages,
            layer_tokens=layer_tokens,
            total_tokens_estimated=total_tokens_estimated,
        )

    async def _build_layer1(self, agent: AgentRegistration) -> str:
        """Layer 1: system prompt + per-agent instruction files + global instruction files."""
        parts: list[str] = []

        # Base system prompt
        if agent.system_prompt:
            parts.append(agent.system_prompt)

        # Per-agent instruction files (from agent.instruction_files JSONB array)
        if agent.instruction_files:
            for file_entry in agent.instruction_files:
                name = file_entry.get("name", "")
                content = file_entry.get("content", "")
                if name and content:
                    parts.append(f"## {name}\n{content}")

        # Global instruction files scoped to this agent's role
        if agent.role:
            role_files = await self._load_instruction_files(scope=f"role:{agent.role}")
            for ifile in role_files:
                parts.append(f"## {ifile.name}\n{ifile.content}")

        # Global instruction files with scope='global'
        global_files = await self._load_instruction_files(scope="global")
        for ifile in global_files:
            parts.append(f"## {ifile.name}\n{ifile.content}")

        return "\n\n---\n\n".join(parts)

    async def _load_instruction_files(self, scope: str) -> list:
        """Load active instruction files for a given scope, ordered by inject_order."""
        from sqlalchemy import select

        from app.db.models.agent_instruction_file import AgentInstructionFile

        result = await self._db.execute(
            select(AgentInstructionFile)
            .where(
                AgentInstructionFile.scope == scope,
                AgentInstructionFile.is_active == True,  # noqa: E712
            )
            .order_by(AgentInstructionFile.inject_order.asc())
        )
        return list(result.scalars().all())

    def _build_layer2(self, agent: AgentRegistration) -> str:
        """Layer 2: methodology block. Skipped if agent.methodology is None."""
        if not agent.methodology:
            return ""
        return f"<methodology>\n{agent.methodology}\n</methodology>"

    def _build_layer3_kb(self) -> str:
        """Layer 3: KB context stub.

        # KB CONTEXT STUB
        Phase 6 will populate this layer with relevant knowledge base pages
        matched by inject_scope to this agent/role. The prompt construction
        structure is ready — this method returns an empty string until then.
        """
        return ""

    async def _build_layer4_alert_context(
        self, context: RuntimeContext
    ) -> str | None:
        """Layer 4: alert context formatted as a user message."""
        if context.alert_id is None:
            return None

        from app.repositories.alert_repository import AlertRepository

        repo = AlertRepository(self._db)
        alert = await repo.get_by_id(context.alert_id)
        if alert is None:
            logger.warning(
                "prompt_builder.alert_not_found", alert_id=context.alert_id
            )
            return None

        # Load related indicators
        indicators = await self._load_alert_indicators(context.alert_id)

        # Build agent-facing alert context dict
        alert_data: dict = {
            "uuid": str(alert.uuid),
            "title": alert.title,
            "severity": alert.severity,
            "status": alert.status,
            "source_name": alert.source_name,
            "description": alert.description,
            "occurred_at": alert.occurred_at.isoformat() if alert.occurred_at else None,
            "enrichment_status": alert.enrichment_status,
            "is_enriched": alert.is_enriched,
            "tags": alert.tags,
            "detection_rule": None,
            "indicators": indicators,
            "agent_findings": alert.agent_findings or [],
        }

        # Include detection rule if present
        if alert.detection_rule:
            alert_data["detection_rule"] = {
                "uuid": str(alert.detection_rule.uuid),
                "name": alert.detection_rule.name,
                "documentation": alert.detection_rule.documentation,
                "mitre_tactics": alert.detection_rule.mitre_tactics,
                "mitre_techniques": alert.detection_rule.mitre_techniques,
            }

        # Include assignment context if available
        if context.assignment_id is not None:
            alert_data["assignment_id"] = context.assignment_id

        return f"<alert_context>\n{json.dumps(alert_data, indent=2, default=str)}\n</alert_context>"

    async def _load_alert_indicators(self, alert_id: int) -> list[dict]:
        """Load indicators associated with an alert, including enrichment results."""
        from sqlalchemy import select

        from app.db.models.alert_indicator import AlertIndicator
        from app.db.models.indicator import Indicator

        result = await self._db.execute(
            select(Indicator)
            .join(AlertIndicator, AlertIndicator.indicator_id == Indicator.id)
            .where(AlertIndicator.alert_id == alert_id)
            .limit(50)
        )
        indicators = list(result.scalars().all())
        return [
            {
                "type": ind.type,
                "value": ind.value,
                "malice": ind.malice,
                "first_seen": ind.first_seen.isoformat() if ind.first_seen else None,
                "last_seen": ind.last_seen.isoformat() if ind.last_seen else None,
                "enrichment_results": ind.enrichment_results or {},
            }
            for ind in indicators
        ]

    def _build_layer6_checkpoint(self, agent: AgentRegistration) -> str:
        """Layer 6: runtime checkpoint with budget info."""
        budget_monthly = agent.budget_monthly_cents
        spent = agent.spent_monthly_cents

        if budget_monthly > 0:
            budget_pct = spent / budget_monthly * 100
            budget_line = (
                f"Budget: ${spent / 100:.2f} of ${budget_monthly / 100:.2f} spent "
                f"({budget_pct:.1f}% used)."
            )
            warning = (
                "\n\u26a0\ufe0f Budget WARNING: approaching limit."
                if budget_pct > 80
                else ""
            )
        else:
            budget_line = "Budget: unlimited (no monthly budget configured)."
            warning = ""

        return f"<runtime_checkpoint>\n{budget_line}{warning}\n</runtime_checkpoint>"

    def _build_messages(
        self,
        layer4_msg: str | None,
        session: AgentTaskSession | None,
    ) -> list[dict]:
        """Assemble the messages list from layer 4 context and session state."""
        messages: list[dict] = []

        if session is None:
            # Fresh session: only the alert context (if any)
            if layer4_msg:
                messages.append({"role": "user", "content": layer4_msg})
            return messages

        session_params = session.session_params or {}

        # Compacted session — handoff summary takes precedence over full history
        handoff = session_params.get("session_handoff_markdown")
        if handoff:
            content = handoff
            if layer4_msg:
                content = f"{layer4_msg}\n\n<session_summary>\n{handoff}\n</session_summary>"
            messages.append({"role": "user", "content": content})
            return messages

        # Resume from full conversation history
        existing_messages = session_params.get("messages")
        if existing_messages:
            messages = list(existing_messages)
            return messages

        # Session exists but no history yet (first run after create)
        if layer4_msg:
            messages.append({"role": "user", "content": layer4_msg})
        return messages
