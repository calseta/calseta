"""AgentRuntimeEngine — executes managed agents via the LLM tool call loop.

Main entry point: AgentRuntimeEngine.run()
Called by: run_managed_agent_task (procrastinate task in app/queue/registry.py)

Responsibilities:
  - Load LLMIntegration and build the provider adapter
  - Resolve or create AgentTaskSession for cross-heartbeat continuity
  - Assemble the 6-layer prompt via PromptBuilder
  - Run the LLM → tool → LLM loop (up to MAX_TOOL_ITERATIONS)
  - Record a CostEvent after every LLM API call
  - Enforce per-alert budget (max_cost_per_alert_cents)
  - Persist conversation state back to agent_task_sessions
  - Update assignment.investigation_state with findings/actions
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from app.integrations.tools.dispatcher import ToolDispatcher
from app.runtime.models import RuntimeContext, RuntimeResult
from app.runtime.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.agent_task_session import AgentTaskSession
    from app.integrations.llm.base import LLMProviderAdapter

logger = structlog.get_logger(__name__)


class AgentRuntimeEngine:
    """Executes managed agents via the LLM tool call loop."""

    MAX_TOOL_ITERATIONS = 50  # Safety limit to prevent infinite loops

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
    ) -> RuntimeResult:
        """Main execution entry point for a managed agent.

        Steps:
        1. Load LLMIntegration (agent.llm_integration_id)
        2. Load or create AgentTaskSession (by agent_id + task_key)
        3. Build prompt via PromptBuilder
        4. Initialize LLMProviderAdapter via factory.get_adapter()
        5. Prepare tools list from agent.tool_ids
        6. Run tool loop
        7. Persist session state to agent_task_sessions
        8. Update assignment.investigation_state with findings/actions
        9. Return RuntimeResult
        """
        log = logger.bind(
            agent_id=agent.id,
            task_key=context.task_key,
            heartbeat_run_id=context.heartbeat_run_id,
        )

        # --- Step 1: Validate managed agent config ---
        if agent.llm_integration_id is None:
            msg = (
                f"Agent {agent.id} has no llm_integration_id configured. "
                "Set llm_integration_id on the agent before running in managed mode."
            )
            log.error("runtime.no_llm_integration")
            return RuntimeResult(success=False, error=msg)

        if agent.execution_mode != "managed":
            msg = (
                f"Agent {agent.id} is not a managed agent "
                f"(execution_mode={agent.execution_mode!r})"
            )
            log.error("runtime.wrong_execution_mode")
            return RuntimeResult(success=False, error=msg)

        # Load LLM integration
        from app.repositories.llm_integration_repository import LLMIntegrationRepository

        llm_repo = LLMIntegrationRepository(self._db)
        integration = await llm_repo.get_by_id(agent.llm_integration_id)
        if integration is None:
            msg = f"LLMIntegration {agent.llm_integration_id} not found for agent {agent.id}"
            log.error("runtime.llm_integration_not_found")
            return RuntimeResult(success=False, error=msg)

        # --- Step 2: Inject skills into agent working directory ---
        await self._inject_skills(agent)

        # --- Step 3: Resolve session ---
        session = await self._resolve_session(agent, context)

        # --- Step 4: Build prompt ---
        builder = PromptBuilder(self._db)
        built = await builder.build(agent=agent, context=context, session=session)

        # --- Step 5: Initialize adapter ---
        from app.integrations.llm.factory import get_adapter

        adapter = get_adapter(integration)

        # --- Step 6: Prepare tools ---
        tools = await self._load_tools(agent)

        # --- Step 7: Run tool loop ---
        log.info(
            "runtime.starting",
            tool_count=len(tools),
            estimated_tokens=built.total_tokens_estimated,
        )

        messages = built.messages
        final_messages, result = await self._run_tool_loop(
            adapter=adapter,
            messages=messages,
            tools=tools,
            system=built.system_prompt,
            agent=agent,
            context=context,
            integration=integration,
        )

        # --- Step 8: Persist session ---
        await self._save_session(
            session=session,
            messages=final_messages,
            result=result,
            heartbeat_run_id=context.heartbeat_run_id,
            integration=integration,
        )

        # --- Step 9: Update assignment investigation_state + release ---
        if context.assignment_id is not None:
            if result.findings or result.actions_proposed:
                await self._update_assignment(
                    assignment_id=context.assignment_id,
                    findings=result.findings,
                    actions_proposed=result.actions_proposed,
                )
            await self._release_assignment(context.assignment_id)

        log.info(
            "runtime.completed",
            success=result.success,
            total_cost_cents=result.total_cost_cents,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            findings_count=len(result.findings),
        )
        return result

    async def _run_tool_loop(
        self,
        adapter: LLMProviderAdapter,
        messages: list[dict],
        tools: list[dict],
        system: str,
        agent: AgentRegistration,
        context: RuntimeContext,
        integration: Any,
    ) -> tuple[list[dict], RuntimeResult]:
        """The core LLM → tool → LLM loop.

        Returns (final_messages, partial_result).
        """
        from app.integrations.llm.base import LLMMessage

        total_cost_cents = 0
        total_input = 0
        total_output = 0
        findings: list[dict] = []
        actions_proposed: list[dict] = []

        dispatcher = ToolDispatcher(db=self._db, agent=agent)

        for iteration in range(self.MAX_TOOL_ITERATIONS):
            logger.debug(
                "runtime.tool_loop_iteration",
                iteration=iteration,
                message_count=len(messages),
                agent_id=agent.id,
            )

            # Call LLM
            llm_messages = [
                LLMMessage(role=m["role"], content=m["content"])
                for m in messages
            ]
            try:
                response = await adapter.create_message(
                    messages=llm_messages,
                    tools=tools,
                    system=system,
                    max_tokens=agent.max_tokens,
                )
            except Exception as exc:
                error_msg = f"LLM API call failed on iteration {iteration}: {exc}"
                logger.error(
                    "runtime.llm_call_failed",
                    iteration=iteration,
                    error=str(exc),
                    agent_id=agent.id,
                )
                return messages, RuntimeResult(
                    success=False,
                    error=error_msg,
                    findings=findings,
                    actions_proposed=actions_proposed,
                    total_cost_cents=total_cost_cents,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            # Accumulate cost
            cost = response.usage
            total_cost_cents += cost.cost_cents
            total_input += cost.input_tokens
            total_output += cost.output_tokens

            # Record cost event in DB
            await self._record_cost(
                agent=agent, context=context, cost=cost, integration=integration
            )

            # Check per-alert budget
            budget_exceeded = (
                agent.max_cost_per_alert_cents > 0
                and total_cost_cents >= agent.max_cost_per_alert_cents
            )
            if budget_exceeded:
                logger.warning(
                    "runtime.per_alert_budget_exceeded",
                    total_cost_cents=total_cost_cents,
                    max_cost_per_alert_cents=agent.max_cost_per_alert_cents,
                    agent_id=agent.id,
                )
                messages.append({"role": "assistant", "content": response.content})
                return messages, RuntimeResult(
                    success=False,
                    error=(
                        f"Per-alert budget exceeded: {total_cost_cents} cents >= "
                        f"{agent.max_cost_per_alert_cents} cents limit."
                    ),
                    findings=findings,
                    actions_proposed=actions_proposed,
                    total_cost_cents=total_cost_cents,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            # Append assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Find tool_use blocks
            # Check tool_use BEFORE end_turn: the Claude Code CLI always returns
            # stop_reason="end_turn" even when it includes tool_use blocks, unlike
            # the Anthropic API which returns "tool_use". Process tools whenever
            # they are present, regardless of stop_reason.
            tool_uses = [
                b for b in response.content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            if not tool_uses:
                logger.debug("runtime.end_turn", iteration=iteration, agent_id=agent.id)
                break

            # Execute tools and collect results
            tool_results: list[dict] = []
            for tool_use in tool_uses:
                tool_id = tool_use.get("name", "")
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use.get("id", "")

                logger.debug(
                    "runtime.dispatching_tool",
                    tool_id=tool_id,
                    tool_use_id=tool_use_id,
                    agent_id=agent.id,
                )

                try:
                    result_data = await dispatcher.dispatch(tool_id, tool_input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result_data, default=str),
                    })
                    # Extract findings/actions from tool results
                    if isinstance(result_data, dict):
                        if "finding" in result_data:
                            findings.append(result_data["finding"])
                        if "action_proposed" in result_data:
                            actions_proposed.append(result_data["action_proposed"])
                        # post_finding tool returns recorded=True with classification
                        data_block = result_data.get("data", {})
                        if isinstance(data_block, dict) and data_block.get("recorded") is True:
                            classification = data_block.get("classification")
                            confidence = data_block.get("confidence")
                            if classification:
                                findings.append({
                                    "classification": classification,
                                    "confidence": confidence,
                                    "alert_uuid": data_block.get("alert_uuid"),
                                })
                except Exception as exc:
                    logger.warning(
                        "runtime.tool_error",
                        tool_id=tool_id,
                        error=str(exc),
                        agent_id=agent.id,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"Tool error: {exc!s}",
                        "is_error": True,
                    })

            # Append tool results as user message
            messages.append({"role": "user", "content": tool_results})

        return messages, RuntimeResult(
            success=True,
            findings=findings,
            actions_proposed=actions_proposed,
            total_cost_cents=total_cost_cents,
            input_tokens=total_input,
            output_tokens=total_output,
        )

    async def _inject_skills(self, agent: AgentRegistration) -> None:
        """Write assigned skills to the agent's working directory as a file tree.

        Each skill is written to a subdirectory:
          {AGENT_FILES_DIR}/{agent.uuid}/skills/{skill.slug}/SKILL.md
          {AGENT_FILES_DIR}/{agent.uuid}/skills/{skill.slug}/references/playbook.md
          ...

        Claude Code picks up skill files from the agent's working directory
        under the ``skills/`` subdirectory. This runs before the LLM loop so
        each invocation gets the current skill set.

        Errors are logged and swallowed — a missing skill file does not abort
        the agent run.
        """
        import os
        from pathlib import Path

        from app.config import settings
        from app.repositories.skill_repository import SkillRepository

        try:
            skill_repo = SkillRepository(self._db)
            assigned_skills = await skill_repo.get_agent_skills(agent.id)
            global_skills = await skill_repo.get_global_skills()

            # Merge: global skills + assigned skills, deduplicated by ID
            seen_ids: set[int] = set()
            skill_list: list = []
            for skill in global_skills + assigned_skills:
                if skill.id not in seen_ids:
                    seen_ids.add(skill.id)
                    skill_list.append(skill)

            if not skill_list:
                return

            base_dir = Path(settings.AGENT_FILES_DIR) / str(agent.uuid) / "skills"

            total_files = 0
            for skill in skill_list:
                # skill.files is loaded via selectin — no extra query needed
                for skill_file in skill.files:
                    file_path = base_dir / skill.slug / skill_file.path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(skill_file.content, encoding="utf-8")
                    total_files += 1

            logger.info(
                "runtime.skills_injected",
                agent_id=agent.id,
                skill_count=len(skill_list),
                file_count=total_files,
                base_dir=str(base_dir),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "runtime.skills_inject_failed",
                agent_id=agent.id,
                error=str(exc),
            )

    async def _load_tools(self, agent: AgentRegistration) -> list[dict]:
        """Load tools assigned to this agent and format for the LLM API.

        Returns tools in Anthropic tool format:
          {"name": ..., "description": ..., "input_schema": ...}
        """
        tool_ids = agent.tool_ids or []
        if not tool_ids:
            return []

        from app.repositories.agent_tool_repository import AgentToolRepository

        repo = AgentToolRepository(self._db)
        tools = await repo.get_by_ids(tool_ids)

        result: list[dict] = []
        for tool in tools:
            # Skip inactive or forbidden tools
            if not tool.is_active or tool.tier == "forbidden":
                continue
            result.append({
                "name": tool.id,
                "description": tool.description,
                "input_schema": tool.input_schema,
            })
        return result

    async def _resolve_session(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
    ) -> AgentTaskSession:
        """Get existing session or create a new one."""
        from app.repositories.agent_task_session_repository import AgentTaskSessionRepository

        repo = AgentTaskSessionRepository(self._db)
        session = await repo.get_by_agent_and_task_key(agent.id, context.task_key)
        if session is None:
            session = await repo.create(
                agent_id=agent.id,
                task_key=context.task_key,
                alert_id=context.alert_id,
            )
        return session

    async def _save_session(
        self,
        session: AgentTaskSession,
        messages: list[dict],
        result: RuntimeResult,
        heartbeat_run_id: int,
        integration: Any,
    ) -> None:
        """Persist conversation state for next heartbeat."""
        from app.repositories.agent_task_session_repository import AgentTaskSessionRepository

        repo = AgentTaskSessionRepository(self._db)

        session_params = dict(session.session_params or {})
        session_params["messages"] = messages

        if result.session_id:
            session_params["session_id"] = result.session_id

        # Check if compaction is needed (80% of context window)
        new_total_input = session.total_input_tokens + result.input_tokens
        new_total_output = session.total_output_tokens + result.output_tokens
        total_tokens = new_total_input + new_total_output

        # Read context window size from integration config, default 200k
        context_window: int = 200_000
        if integration and integration.config:
            context_window = int(integration.config.get("context_window", context_window))

        if total_tokens > context_window * 0.8:
            # Mark for compaction on next run
            session_params["needs_compaction"] = True
            logger.info(
                "runtime.session_compaction_flagged",
                total_tokens=total_tokens,
                context_window=context_window,
                agent_id=session.agent_registration_id,
            )

        await repo.update(
            session,
            session_params=session_params,
            total_input_tokens=new_total_input,
            total_output_tokens=new_total_output,
            total_cost_cents=session.total_cost_cents + result.total_cost_cents,
            heartbeat_count=session.heartbeat_count + 1,
            last_run_id=heartbeat_run_id,
            last_error=result.error,
        )

    async def _record_cost(
        self,
        agent: AgentRegistration,
        context: RuntimeContext,
        cost: Any,
        integration: Any,
    ) -> None:
        """Persist a CostEvent row for this LLM API call."""
        from app.repositories.cost_event_repository import CostEventRepository

        repo = CostEventRepository(self._db)
        provider = integration.provider if integration else "unknown"
        model = integration.model if integration else "unknown"

        try:
            await repo.create(
                agent_id=agent.id,
                llm_integration_id=integration.id if integration else None,
                alert_id=context.alert_id,
                heartbeat_run_id=context.heartbeat_run_id,
                provider=provider,
                model=model,
                input_tokens=cost.input_tokens,
                output_tokens=cost.output_tokens,
                cost_cents=cost.cost_cents,
                billing_type=cost.billing_type,
            )
        except Exception as exc:
            # Cost recording failure should never abort the agent run
            logger.error(
                "runtime.cost_record_failed",
                error=str(exc),
                agent_id=agent.id,
            )

    async def _update_assignment(
        self,
        assignment_id: int,
        findings: list[dict],
        actions_proposed: list[dict],
    ) -> None:
        """Update assignment.investigation_state with accumulated findings."""
        from app.repositories.alert_assignment_repository import AlertAssignmentRepository

        repo = AlertAssignmentRepository(self._db)
        assignment = await repo.get_by_id(assignment_id)
        if assignment is None:
            return

        current_state = dict(assignment.investigation_state or {})
        existing_findings = current_state.get("findings", [])
        existing_actions = current_state.get("actions_proposed", [])

        current_state["findings"] = existing_findings + findings
        current_state["actions_proposed"] = existing_actions + actions_proposed
        current_state["last_updated"] = datetime.now(UTC).isoformat()

        await repo.patch(assignment, investigation_state=current_state)

    async def _release_assignment(self, assignment_id: int) -> None:
        """Set assignment status to 'released' when the agent run completes."""
        from app.repositories.alert_assignment_repository import AlertAssignmentRepository

        repo = AlertAssignmentRepository(self._db)
        assignment = await repo.get_by_id(assignment_id)
        if assignment is None:
            return
        try:
            await repo.release(assignment)
            await self._db.flush()
        except Exception as exc:
            logger.warning(
                "runtime.release_assignment_failed",
                assignment_id=assignment_id,
                error=str(exc),
            )
