"""
Session compaction — summarize long conversation histories to save tokens.

When a session is flagged with ``needs_compaction=True`` (set by the engine
when total tokens > 80% of context window), this service:

1. Sends the full message history to the agent's LLM for summarization
2. Saves the summary as ``session_handoff_markdown``
3. Clears ``messages`` from session_params
4. Resets ``needs_compaction`` and sets ``compacted_at``

If the compaction LLM call fails, the run proceeds with full messages
(compaction is best-effort, never blocks execution).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.db.models.agent_task_session import AgentTaskSession
    from app.integrations.llm.base import LLMProviderAdapter

logger = structlog.get_logger(__name__)

_COMPACTION_SYSTEM_PROMPT = """\
You are a security operations assistant. Summarize the following \
investigation conversation into a concise handoff document.

Focus on:
- Key findings and their evidence
- Actions taken (tools called, workflows executed)
- Current investigation status and next steps
- Any analyst input or directives given

Format as structured markdown. Maximum 2000 tokens.
Do NOT include raw JSON payloads or full tool outputs — summarize them.
"""

_MAX_SUMMARY_CHARS = 8000  # ~2000 tokens


async def compact_session(
    session: AgentTaskSession,
    adapter: LLMProviderAdapter,
    *,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Run compaction on a session and return updated session_params.

    Returns the modified session_params dict (caller persists it).
    Also returns the CostInfo from the compaction call for cost tracking.

    Returns:
        dict with keys:
          - ``session_params``: updated session params
          - ``cost``: CostInfo from the compaction LLM call (or None)
          - ``compacted``: bool — whether compaction actually ran
    """
    from app.integrations.llm.base import LLMMessage

    session_params = dict(session.session_params or {})
    messages = session_params.get("messages", [])

    if not messages:
        logger.debug(
            "compaction.no_messages",
            session_id=session.id,
        )
        return {
            "session_params": session_params,
            "cost": None,
            "compacted": False,
        }

    # Build the conversation text for summarization
    conversation_text = _serialize_messages_for_summary(messages)

    try:
        response = await adapter.create_message(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        "Summarize this SOC investigation conversation:\n\n"
                        f"{conversation_text}"
                    ),
                ),
            ],
            tools=[],
            system=_COMPACTION_SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )

        # Extract text from response content
        summary = _extract_text(response.content)
        if not summary:
            logger.warning("compaction.empty_summary", session_id=session.id)
            return {
                "session_params": session_params,
                "cost": response.usage,
                "compacted": False,
            }

        # Truncate if needed
        summary = summary[:_MAX_SUMMARY_CHARS]

        # Update session params
        session_params["session_handoff_markdown"] = summary
        session_params.pop("messages", None)
        session_params["needs_compaction"] = False
        session_params["compacted_at"] = datetime.now(UTC).isoformat()

        logger.info(
            "compaction.completed",
            session_id=session.id,
            summary_length=len(summary),
            original_message_count=len(messages),
        )

        return {
            "session_params": session_params,
            "cost": response.usage,
            "compacted": True,
        }

    except Exception as exc:
        logger.warning(
            "compaction.llm_call_failed",
            session_id=session.id,
            error=str(exc),
        )
        # Proceed with full messages — don't block the run
        return {
            "session_params": session_params,
            "cost": None,
            "compacted": False,
        }


def _serialize_messages_for_summary(messages: list[dict]) -> str:
    """Convert message list into readable text for summarization."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content[:3000]}")
        elif isinstance(content, list):
            # Tool results or content blocks
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_result":
                        tool_content = block.get("content", "")
                        parts.append(
                            f"[{role}/tool_result]: {str(tool_content)[:1000]}"
                        )
                    elif block.get("type") == "text":
                        parts.append(
                            f"[{role}]: {block.get('text', '')[:3000]}"
                        )
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = json.dumps(
                            block.get("input", {}), default=str,
                        )[:500]
                        parts.append(f"[{role}/tool_use]: {name}({inp})")
    return "\n\n".join(parts)


def _extract_text(content: Any) -> str:
    """Extract text from LLM response content (string or content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    return str(content)
