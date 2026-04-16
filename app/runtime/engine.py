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
        2. Inject skills into ephemeral temp dir (cleaned up in finally)
        3. Load or create AgentTaskSession (by agent_id + task_key)
        4. Build prompt via PromptBuilder
        5. Initialize LLMProviderAdapter via factory.get_adapter()
        6. Prepare tools list from agent.tool_ids
        7. Run tool loop
        8. Persist session state to agent_task_sessions
        9. Update assignment.investigation_state with findings/actions
        10. Return RuntimeResult
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

        # --- Step 2: Inject skills into ephemeral temp dir (C6) ---
        skills_tmpdir = await self._inject_skills_ephemeral(agent)

        try:
            # --- Step 3: Resolve session ---
            session = await self._resolve_session(agent, context)

            # --- Step 3b: Initialize adapter (needed for compaction) ---
            from app.integrations.llm.factory import get_adapter

            adapter = get_adapter(integration)

            # --- Step 3c: Session compaction (C4) ---
            session = await self._maybe_compact_session(
                session, adapter, agent, context,
            )

            # --- Step 4: Build prompt ---
            builder = PromptBuilder(self._db)
            built = await builder.build(
                agent=agent, context=context, session=session,
            )

            # --- Step 5: adapter already initialized above ---

            # --- Step 6: Prepare tools ---
            tools = await self._load_tools(agent)

            # --- Step 6b: Initialize run log store ---
            log_handle = None
            log_store = None
            event_seq = 0
            try:
                from app.config import settings
                from app.services.run_log_store import RunLogStore

                if context.run_uuid is not None:
                    log_store = RunLogStore(settings.CALSETA_DATA_DIR)
                    log_handle = log_store.open(
                        agent.uuid, context.run_uuid,
                    )
            except Exception as exc:
                log.warning(
                    "runtime.log_store_init_failed", error=str(exc),
                )

            async def _on_log(stream: str, chunk: str) -> None:
                """Write event to NDJSON file and DB."""
                import contextlib

                nonlocal event_seq
                event_seq += 1
                etype = (
                    "llm_response" if stream == "assistant" else stream
                )
                event_data = {
                    "event_type": etype,
                    "stream": stream,
                    "content": chunk[:10_000],
                }
                # Write to NDJSON file (non-blocking)
                if log_handle is not None and log_store is not None:
                    with contextlib.suppress(Exception):
                        log_store.append(log_handle, event_data)
                # Write to DB + NOTIFY (non-blocking)
                with contextlib.suppress(Exception):
                    from app.repositories.run_event_repository import (
                        RunEventRepository,
                    )
                    repo = RunEventRepository(self._db)
                    await repo.create_event(
                        heartbeat_run_id=context.heartbeat_run_id,
                        seq=event_seq,
                        event_type=etype,
                        stream=stream,
                        content=chunk[:10_000],
                    )
                    from app.services.run_event_stream import (
                        notify_run_event,
                    )
                    await notify_run_event(
                        self._db, context.heartbeat_run_id,
                        event_seq, event_data,
                    )

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
                on_log=_on_log,
            )

            # --- Step 7b: Finalize run log ---
            log_sha256 = None
            log_bytes = None
            log_ref = None
            if log_handle is not None and log_store is not None:
                try:
                    log_sha256, log_bytes = log_store.finalize(
                        log_handle,
                    )
                    log_ref = str(log_handle.path)
                except Exception as exc:
                    log.warning(
                        "runtime.log_finalize_failed", error=str(exc),
                    )

            # Update HeartbeatRun with log metadata
            if log_sha256 is not None:
                try:
                    from app.repositories.heartbeat_run_repository import (
                        HeartbeatRunRepository,
                    )
                    hr_repo = HeartbeatRunRepository(self._db)
                    run_obj = await hr_repo.get_by_id(
                        context.heartbeat_run_id,
                    )
                    if run_obj is not None:
                        await hr_repo.update_status(
                            run_obj,
                            run_obj.status,
                            log_ref=log_ref,
                            log_sha256=log_sha256,
                            log_bytes=log_bytes,
                        )
                except Exception as exc:
                    log.warning(
                        "runtime.log_metadata_update_failed",
                        error=str(exc),
                    )

            # --- Step 8: Persist session ---
            await self._save_session(
                session=session,
                messages=final_messages,
                result=result,
                heartbeat_run_id=context.heartbeat_run_id,
                integration=integration,
            )

            # --- Step 9: Update assignment state + release ---
            if context.assignment_id is not None:
                if result.findings or result.actions_proposed:
                    await self._update_assignment(
                        assignment_id=context.assignment_id,
                        findings=result.findings,
                        actions_proposed=result.actions_proposed,
                    )
                await self._release_assignment(context.assignment_id)

            # --- Step 9b: Clear cancellation flag ---
            from app.services.run_cancellation import clear_cancellation
            clear_cancellation(context.heartbeat_run_id)

            log.info(
                "runtime.completed",
                success=result.success,
                total_cost_cents=result.total_cost_cents,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                findings_count=len(result.findings),
            )
            return result

        finally:
            # C6: Clean up ephemeral skill temp directory
            if skills_tmpdir is not None:
                import shutil
                try:
                    shutil.rmtree(skills_tmpdir, ignore_errors=True)
                    log.debug(
                        "runtime.skills_tmpdir_cleaned",
                        tmpdir=skills_tmpdir,
                    )
                except Exception:
                    pass

    async def _run_tool_loop(
        self,
        adapter: LLMProviderAdapter,
        messages: list[dict],
        tools: list[dict],
        system: str,
        agent: AgentRegistration,
        context: RuntimeContext,
        integration: Any,
        on_log: Any = None,
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

            # Check cancellation flag (for API-based adapters)
            from app.services.run_cancellation import is_cancelled

            if is_cancelled(context.heartbeat_run_id):
                logger.info(
                    "runtime.cancelled",
                    iteration=iteration,
                    agent_id=agent.id,
                )
                return messages, RuntimeResult(
                    success=False,
                    error="Run cancelled by user.",
                    findings=findings,
                    actions_proposed=actions_proposed,
                    total_cost_cents=total_cost_cents,
                    input_tokens=total_input,
                    output_tokens=total_output,
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
                    on_log=on_log,
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
            # Emit budget_check event
            if on_log is not None:
                import contextlib
                with contextlib.suppress(Exception):
                    await on_log(
                        "budget_check",
                        f"cost={total_cost_cents}c"
                        f" / {agent.max_cost_per_alert_cents}c",
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

                # Emit tool_call event
                if on_log is not None:
                    import contextlib
                    with contextlib.suppress(Exception):
                        args_str = json.dumps(tool_input, default=str)[:500]
                        await on_log("tool_call", f"{tool_id}({args_str})")

                try:
                    result_data = await dispatcher.dispatch(tool_id, tool_input)
                    result_str = json.dumps(result_data, default=str)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_str,
                    })

                    # Emit tool_result event
                    if on_log is not None:
                        import contextlib
                        with contextlib.suppress(Exception):
                            await on_log("tool_result", result_str[:2000])

                    # Extract findings/actions from tool results
                    if isinstance(result_data, dict):
                        if "finding" in result_data:
                            findings.append(result_data["finding"])
                            if on_log is not None:
                                import contextlib
                                with contextlib.suppress(Exception):
                                    await on_log(
                                        "finding",
                                        json.dumps(result_data["finding"], default=str),
                                    )
                        if "action_proposed" in result_data:
                            actions_proposed.append(result_data["action_proposed"])
                        # post_finding tool returns recorded=True
                        data_block = result_data.get("data", {})
                        if isinstance(data_block, dict) and data_block.get("recorded") is True:
                            classification = data_block.get("classification")
                            confidence = data_block.get("confidence")
                            if classification:
                                finding = {
                                    "classification": classification,
                                    "confidence": confidence,
                                    "alert_uuid": data_block.get("alert_uuid"),
                                }
                                findings.append(finding)
                                if on_log is not None:
                                    import contextlib
                                    with contextlib.suppress(Exception):
                                        await on_log(
                                            "finding",
                                            json.dumps(finding, default=str),
                                        )
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

    async def _inject_skills_ephemeral(
        self, agent: AgentRegistration
    ) -> str | None:
        """C6: Write assigned skills to an ephemeral temp directory.

        Returns the temp directory path (for Claude Code ``--add-dir``),
        or None if no skills are assigned. The caller is responsible for
        cleaning up the temp dir in a ``finally`` block.

        For API-based adapters, skill content is injected into the system
        prompt instead — no temp dir needed.
        """
        import tempfile
        from pathlib import Path

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
                return None

            tmpdir = tempfile.mkdtemp(prefix="calseta-skills-")
            base_dir = Path(tmpdir)

            total_files = 0
            for skill in skill_list:
                for skill_file in skill.files:
                    file_path = base_dir / skill.slug / skill_file.path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(
                        skill_file.content, encoding="utf-8"
                    )
                    total_files += 1

            logger.info(
                "runtime.skills_injected_ephemeral",
                agent_id=agent.id,
                skill_count=len(skill_list),
                file_count=total_files,
                tmpdir=tmpdir,
            )
            return tmpdir
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "runtime.skills_inject_failed",
                agent_id=agent.id,
                error=str(exc),
            )
            return None

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

    async def _maybe_compact_session(
        self,
        session: AgentTaskSession,
        adapter: LLMProviderAdapter,
        agent: AgentRegistration,
        context: RuntimeContext,
    ) -> AgentTaskSession:
        """C4: Run session compaction if flagged.

        Returns the (possibly updated) session object. If compaction
        fails, the original session is returned unchanged.
        """
        session_params = session.session_params or {}
        if not session_params.get("needs_compaction"):
            return session

        logger.info(
            "runtime.compaction_starting",
            agent_id=agent.id,
            session_id=session.id,
        )

        from app.services.session_compaction import compact_session

        result = await compact_session(session, adapter)

        if result["compacted"]:
            # Persist compacted session params
            from app.repositories.agent_task_session_repository import (
                AgentTaskSessionRepository,
            )
            repo = AgentTaskSessionRepository(self._db)
            await repo.update(session, session_params=result["session_params"])

            # Record compaction cost if available
            if result["cost"] is not None:
                await self._record_cost(
                    agent=agent,
                    context=context,
                    cost=result["cost"],
                    integration=None,
                )

            # Refresh session to pick up updated params
            await self._db.refresh(session)

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
