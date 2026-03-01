"""
Workflow sandbox — safely compile and execute a workflow's run() function.

This module is the lowest-level execution primitive. It:
  1. Compiles the code string
  2. Builds a restricted globals namespace (no dangerous builtins)
  3. exec()s the code into that namespace
  4. Retrieves the run() coroutine
  5. Wraps execution in asyncio.wait_for to enforce timeout_seconds
  6. Catches ALL exceptions and returns WorkflowResult.fail() — never raises

The sandbox does NOT create WorkflowContext — that is the executor's job.
"""

from __future__ import annotations

import asyncio
import builtins
import traceback
from typing import Any

from app.workflows.context import WorkflowContext, WorkflowResult

# ---------------------------------------------------------------------------
# Restricted builtins namespace
# ---------------------------------------------------------------------------

# Allow common builtins but strip dangerous ones
_BLOCKED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        # Note: __import__ is NOT blocked here — Python's import machinery needs it
        # for `import` and `from ... import` statements to work. Security over which
        # modules may be imported is enforced by validate_workflow_code() at save time.
        "open",
        "exec",
        "eval",
        "compile",
        "breakpoint",
        "input",
        "memoryview",
    }
)

_SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in dir(builtins)
    if name not in _BLOCKED_BUILTIN_NAMES and not name.startswith("__")
}
# Re-add essential dunder names needed by Python's import machinery and module loading
for _dunder in ("__name__", "__doc__", "__package__", "__loader__", "__spec__", "__import__"):
    _safe_val = getattr(builtins, _dunder, None)
    if _safe_val is not None:
        _SAFE_BUILTINS[_dunder] = _safe_val
    else:
        _SAFE_BUILTINS[_dunder] = None


# ---------------------------------------------------------------------------
# run_workflow_code
# ---------------------------------------------------------------------------


async def run_workflow_code(
    code: str,
    ctx: WorkflowContext,
    timeout: int,
) -> WorkflowResult:
    """
    Execute workflow code in a restricted sandbox.

    Args:
        code:    The full Python source of the workflow module.
        ctx:     The WorkflowContext to inject as the `ctx` parameter to run().
        timeout: Maximum execution time in seconds; enforced via asyncio.wait_for.

    Returns:
        WorkflowResult. Never raises.
    """
    # Step 1: compile
    try:
        code_obj = compile(code, "<workflow>", "exec")
    except SyntaxError as exc:
        return WorkflowResult.fail(f"Workflow code syntax error: {exc}")

    # Step 2: build restricted namespace
    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

    # Step 3: exec code into namespace
    try:
        exec(code_obj, namespace)  # noqa: S102
    except Exception as exc:
        return WorkflowResult.fail(
            f"Workflow code raised an exception during module load: {exc}\n"
            + traceback.format_exc()
        )

    # Step 4: retrieve run()
    run_fn = namespace.get("run")
    if run_fn is None or not asyncio.iscoroutinefunction(run_fn):
        return WorkflowResult.fail(
            "Workflow code does not define an async function named 'run'"
        )

    # Step 5: execute with timeout
    try:
        result = await asyncio.wait_for(run_fn(ctx), timeout=float(timeout))
    except TimeoutError:
        return WorkflowResult.fail(
            f"Workflow execution timed out after {timeout} seconds"
        )
    except Exception as exc:
        return WorkflowResult.fail(
            f"Workflow run() raised an exception: {exc}\n" + traceback.format_exc()
        )

    # Step 6: validate result type
    if not isinstance(result, WorkflowResult):
        return WorkflowResult.fail(
            f"Workflow run() returned unexpected type: {type(result).__name__}. "
            "Must return a WorkflowResult instance."
        )

    return result
