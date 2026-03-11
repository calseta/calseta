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
import contextlib
import resource as _resource
import traceback
from typing import Any

import structlog

from app.workflows.context import WorkflowContext, WorkflowResult

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowed modules (must match _ALLOWED_IMPORTS in workflow_ast.py)
# ---------------------------------------------------------------------------

_ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "asyncio",
        "base64",
        "collections",
        "copy",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "hmac",
        "html",
        "http",
        "inspect",
        "ipaddress",
        "itertools",
        "json",
        "logging",
        "math",
        "operator",
        "re",
        "statistics",
        "string",
        "textwrap",
        "time",
        "typing",
        "typing_extensions",
        "unicodedata",
        "urllib",
        "uuid",
        # Calseta workflow SDK
        "calseta",
        "app",
    }
)

# ---------------------------------------------------------------------------
# Restricted __import__ — runtime enforcement of module whitelist
# ---------------------------------------------------------------------------

_real_import = builtins.__import__


def _restricted_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    """A restricted __import__ that only allows whitelisted modules.

    This provides runtime enforcement in addition to the AST-level validation
    performed by validate_workflow_code() at save time. Even if a workflow
    somehow bypasses AST checks, the sandbox will block disallowed imports.
    """
    # Allow relative imports (level > 0) — these resolve within the already-loaded module
    if level == 0 and name.split(".")[0] not in _ALLOWED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed in workflows")
    return _real_import(name, globals, locals, fromlist, level)


# ---------------------------------------------------------------------------
# Restricted builtins namespace
# ---------------------------------------------------------------------------

# Allow common builtins but strip dangerous ones (including __import__)
_BLOCKED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "__import__",
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
# Re-add essential dunder names needed by Python's module loading (but NOT __import__)
for _dunder in ("__name__", "__doc__", "__package__", "__loader__", "__spec__"):
    _safe_val = getattr(builtins, _dunder, None)
    if _safe_val is not None:
        _SAFE_BUILTINS[_dunder] = _safe_val
    else:
        _SAFE_BUILTINS[_dunder] = None

# Inject the restricted __import__ so import/from statements work only for allowed modules
_SAFE_BUILTINS["__import__"] = _restricted_import


# ---------------------------------------------------------------------------
# Resource limits — memory ceiling for workflow execution
# ---------------------------------------------------------------------------


def _set_memory_limit(max_bytes: int) -> tuple[int, tuple[int, int]] | None:
    """Set a virtual memory ceiling and return (rlimit_const, previous_limit), or None.

    On Linux, uses RLIMIT_AS (virtual address space).
    On macOS, RLIMIT_AS is not available; falls back to RLIMIT_RSS (resident set size)
    which is advisory but better than nothing.
    If neither works, returns None and execution proceeds without a memory limit.
    """
    for limit_attr in ("RLIMIT_AS", "RLIMIT_RSS"):
        rlimit = getattr(_resource, limit_attr, None)
        if rlimit is None:
            continue
        try:
            soft, hard = _resource.getrlimit(rlimit)
            # Never exceed the hard limit
            effective = min(max_bytes, hard) if hard != _resource.RLIM_INFINITY else max_bytes
            _resource.setrlimit(rlimit, (effective, hard))
            logger.debug(
                "workflow_memory_limit_set",
                limit_type=limit_attr,
                max_mb=max_bytes // (1024 * 1024),
            )
            return (rlimit, (soft, hard))
        except (ValueError, OSError) as exc:
            logger.debug(
                "workflow_memory_limit_skip",
                limit_type=limit_attr,
                reason=str(exc),
            )
            continue
    return None


def _restore_memory_limit(saved: tuple[int, tuple[int, int]] | None) -> None:
    """Restore the memory limit saved by _set_memory_limit."""
    if saved is None:
        return
    rlimit, prev_limit = saved
    with contextlib.suppress(ValueError, OSError):
        _resource.setrlimit(rlimit, prev_limit)


# ---------------------------------------------------------------------------
# run_workflow_code
# ---------------------------------------------------------------------------


async def run_workflow_code(
    code: str,
    ctx: WorkflowContext,
    timeout: int,
    max_memory_mb: int = 256,
) -> WorkflowResult:
    """
    Execute workflow code in a restricted sandbox.

    Args:
        code:           The full Python source of the workflow module.
        ctx:            The WorkflowContext to inject as the `ctx` parameter to run().
        timeout:        Maximum execution time in seconds; enforced via asyncio.wait_for.
        max_memory_mb:  Maximum memory in MB for the workflow execution (default 256).

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

    # Step 5: execute with timeout and memory limits
    max_bytes = max_memory_mb * 1024 * 1024
    prev_limit = _set_memory_limit(max_bytes)
    if prev_limit is None:
        logger.warning(
            "workflow_memory_limit_unavailable",
            reason="resource limits not supported on this platform",
        )
    try:
        result = await asyncio.wait_for(run_fn(ctx), timeout=float(timeout))
    except MemoryError:
        return WorkflowResult.fail(
            f"Workflow exceeded memory limit ({max_memory_mb}MB)"
        )
    except TimeoutError:
        return WorkflowResult.fail(
            f"Workflow execution timed out after {timeout} seconds"
        )
    except Exception as exc:
        return WorkflowResult.fail(
            f"Workflow run() raised an exception: {exc}\n" + traceback.format_exc()
        )
    finally:
        _restore_memory_limit(prev_limit)

    # Step 6: validate result type
    if not isinstance(result, WorkflowResult):
        return WorkflowResult.fail(
            f"Workflow run() returned unexpected type: {type(result).__name__}. "
            "Must return a WorkflowResult instance."
        )

    return result
