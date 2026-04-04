"""PromptBuilder — assembles the 6-layer prompt for a managed agent invocation.

Layer order:
  Layer 1: agent.system_prompt + per-agent instruction_files + global instruction_files
  Layer 2: agent.methodology (wrapped in <methodology> tags)
  Layer 3: KB context — global + role-scoped + agent-specific pages, token-budget capped
  Layer 4: Alert/task context — assembled as the first user message
  Layer 5: Session state — injected into messages list
  Layer 6: Runtime checkpoint + agent memory (budget-capped, sorted by staleness/relevance)

Final structure:
  system_prompt = layer1 + layer2 + layer3 + layer6(checkpoint + memory)
  messages = [layer4_user_msg, ...layer5_history...]
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

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


def _xml_escape(text: str) -> str:
    """Escape special XML/HTML characters for use in attribute values."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _is_memory_stale(page: object, now: datetime) -> bool:
    """Check if a memory page is stale based on staleness_ttl_hours in metadata."""
    metadata = getattr(page, "metadata_", None) or {}
    ttl_hours = metadata.get("staleness_ttl_hours")
    updated_at = getattr(page, "updated_at", None)
    if ttl_hours and updated_at:
        updated = updated_at.replace(tzinfo=UTC) if updated_at.tzinfo is None else updated_at
        return bool((now - updated).total_seconds() / 3600 > float(ttl_hours))
    return False

# KB injection budget: 15% of context window by default
_KB_BUDGET_PCT = 0.15

# Memory injection budget: 5% of context window by default
_MEMORY_BUDGET_PCT = 0.05


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

        context_window = getattr(agent, "max_tokens", None) or 200_000

        layer1 = await self._build_layer1(agent)
        layer2 = self._build_layer2(agent)
        layer3, layer3_tokens = await self._build_layer3_kb(agent, context_window)
        layer4_msg = await self._build_layer4_alert_context(context)
        layer6 = await self._build_layer6_checkpoint(agent, context_window)

        # Assemble system prompt: layers 1 + 2 + 3 + 6
        system_parts = [layer1]
        if layer2:
            system_parts.append(layer2)
        if layer3:
            system_parts.append(layer3)
        system_parts.append(layer6)
        system_prompt = "\n\n".join(p for p in system_parts if p)

        # Assemble messages list from layer 4 + layer 5
        messages = self._build_messages(layer4_msg, session)

        # Token estimates per layer
        layer_tokens: dict[str, int] = {
            "layer1_system": _estimate_tokens(layer1),
            "layer2_methodology": _estimate_tokens(layer2),
            "layer3_kb": layer3_tokens,
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

    async def _build_layer3_kb(
        self, agent: AgentRegistration, context_window: int
    ) -> tuple[str, int]:
        """Layer 3: KB context — global + role-scoped + agent-specific pages.

        Returns (xml_block, token_count). Empty string if no injectable pages exist.
        Budget: KB_BUDGET_PCT of context_window. Pinned pages always included.
        """
        try:
            from app.repositories.kb_repository import KBPageRepository

            repo = KBPageRepository(self._db)
            pages = await repo.get_injectable_pages(
                agent_uuid=str(agent.uuid),
                agent_role=agent.role,
            )

            if not pages:
                return "", 0

            budget = int(context_window * _KB_BUDGET_PCT)
            parts: list[str] = []
            total_tokens = 0

            for page in pages:
                tokens = page.token_count or _estimate_tokens(page.body)
                if page.inject_pinned or total_tokens + tokens <= budget:
                    updated = page.updated_at.strftime("%Y-%m-%d") if page.updated_at else ""
                    parts.append(
                        f'<context_document title="{_xml_escape(page.title)}" '
                        f'slug="{_xml_escape(page.slug)}" updated="{updated}">\n'
                        f"{page.body}\n"
                        f"</context_document>"
                    )
                    total_tokens += tokens

            if not parts:
                return "", 0

            block = "\n\n".join(parts)
            return block, _estimate_tokens(block)

        except Exception as exc:
            logger.warning("prompt_builder.layer3_kb_failed", error=str(exc))
            return "", 0

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

    async def _build_layer6_checkpoint(
        self, agent: AgentRegistration, context_window: int
    ) -> str:
        """Layer 6: runtime checkpoint + agent persistent memory.

        Includes:
        - Budget status
        - Agent memory entries (budget-capped at MEMORY_BUDGET_PCT of context window)
          Sorted: non-stale first, then by updated_at DESC.
          Stale entries are included with a [STALE] prefix.
        """
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

        checkpoint_text = f"{budget_line}{warning}"

        # Inject agent memory entries
        memory_block = await self._build_memory_block(agent, context_window)

        parts = [f"<runtime_checkpoint>\n{checkpoint_text}\n</runtime_checkpoint>"]
        if memory_block:
            parts.append(memory_block)

        return "\n\n".join(parts)

    async def _build_memory_block(
        self, agent: AgentRegistration, context_window: int
    ) -> str:
        """Load and format agent memory entries for Layer 6 injection.

        Sorted: non-stale DESC, updated_at DESC.
        Stale entries get [STALE — last updated X hours ago] prefix.
        Budget: MEMORY_BUDGET_PCT of context_window.
        """
        try:
            from sqlalchemy import and_, select

            from app.db.models.kb_page import KnowledgeBasePage

            agent_folder = f"/memory/agents/{agent.id}/"

            result = await self._db.execute(
                select(KnowledgeBasePage)
                .where(
                    and_(
                        KnowledgeBasePage.folder == agent_folder,
                        KnowledgeBasePage.status == "published",
                    )
                )
                .order_by(KnowledgeBasePage.updated_at.desc())
            )
            pages = list(result.scalars().all())

            if not pages:
                return ""

            now = datetime.now(UTC)
            budget = int(context_window * _MEMORY_BUDGET_PCT)

            # Annotate each page with staleness
            annotated: list[tuple[bool, KnowledgeBasePage]] = []
            for page in pages:
                is_stale = _is_memory_stale(page, now)
                annotated.append((is_stale, page))

            # Sort: non-stale first, then by recency
            annotated.sort(
                key=lambda x: (x[0], -(x[1].updated_at.timestamp() if x[1].updated_at else 0))
            )

            parts: list[str] = []
            total_tokens = 0

            for is_stale, page in annotated:
                tokens = page.token_count or _estimate_tokens(page.body)
                if total_tokens + tokens > budget:
                    break

                body = page.body
                if is_stale and page.updated_at:
                    uat = page.updated_at
                    if uat.tzinfo is None:
                        uat = uat.replace(tzinfo=UTC)
                    hours_ago = int((now - uat).total_seconds() / 3600)
                    body = f"[STALE — last updated {hours_ago} hours ago]\n{body}"

                title = page.title or page.slug
                parts.append(
                    f'<memory title="{_xml_escape(title)}" slug="{_xml_escape(page.slug)}"'
                    f' stale="{str(is_stale).lower()}">\n{body}\n</memory>'
                )
                total_tokens += tokens

            if not parts:
                return ""

            return "<agent_memory>\n" + "\n\n".join(parts) + "\n</agent_memory>"

        except Exception as exc:
            logger.warning("prompt_builder.memory_injection_failed", error=str(exc))
            return ""

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
