"""
Workflow process-isolation runner (Wave 5 / S1).

Public surface:

    async def run_workflow_isolated(
        code: str,
        ctx_payload: dict,
        *,
        timeout_seconds: int,
        memory_mb: int = 256,
    ) -> WorkflowResult

Spawns ``scripts/workflow_subprocess_entry.py`` as a separate OS process with:
  * a scrubbed environment (``PATH`` and ``LANG`` only)
  * a per-run scratch directory passed as cwd (cleaned up in ``finally``)
  * pipes for NDJSON IPC on stdin/stdout, stderr captured to a buffer
  * wall-clock timeout enforced via ``asyncio.wait_for``

The runner serves IPC ops issued by the child:
  * ``http.request``  — proxied via httpx with the same SSRF gate the
    in-process executor uses (``app.services.url_validation``).
  * ``secret.get``    — minimal v1: returns ``os.environ`` lookup.  S3
    will replace this with allowlist-aware resolution.
  * ``log``           — appends to the parent-side log stream.
  * ``done``          — final result; loop exits.

Failure modes are mapped to ``WorkflowResult.fail`` with structured reasons:
``timeout``, ``child_crashed``, ``resource_limit_exceeded``, ``ssrf_blocked``,
``ipc_protocol_error``.

Mimics the ``claude_code_adapter`` subprocess pattern for streaming and clean
shutdown — see ``app/integrations/llm/claude_code_adapter.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
import structlog

from app.workflows.context import WorkflowResult

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# IPC protocol version — must match the child.
# ---------------------------------------------------------------------------

IPC_PROTOCOL_VERSION = "1"

# Hard cap on bytes consumed from the child's stdout/stderr.  A pathological
# child must not be allowed to exhaust API memory by streaming garbage.
MAX_CHILD_OUTPUT_BYTES = 64 * 1024 * 1024  # 64 MiB

# Minimal env passed to the child.  Everything else is scrubbed; S3 will add
# the per-workflow secret allowlist.
_ALLOWED_CHILD_ENV_VARS: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "TZ")


# ---------------------------------------------------------------------------
# Detect whether the child platform supports seccomp.  Used to (a) pick the
# correct ``WORKFLOW_ISOLATION_MODE`` and (b) emit the
# ``workflow.seccomp_unavailable`` event exactly once per process.
# ---------------------------------------------------------------------------

_seccomp_warning_emitted = False


def seccomp_available() -> bool:
    if sys.platform != "linux":
        return False
    try:
        import pyseccomp  # type: ignore[import-not-found]  # noqa: F401

        return True
    except ImportError:
        return False


def _emit_seccomp_warning_once() -> None:
    global _seccomp_warning_emitted
    if _seccomp_warning_emitted:
        return
    _seccomp_warning_emitted = True
    logger.warning(
        "workflow.seccomp_unavailable",
        platform=sys.platform,
        message=(
            "pyseccomp is not available on this platform; workflow subprocess "
            "isolation will fall back to rlimit-only confinement"
        ),
    )


# ---------------------------------------------------------------------------
# Container for the parent-side context payload that the runner needs.  The
# caller (workflow_executor) builds this from the DB; the runner serializes
# it to a single ``init`` message.
# ---------------------------------------------------------------------------


@dataclass
class WorkflowRunInputs:
    """Plain-data view of WorkflowContext, safe to JSON-serialize."""

    indicator: dict[str, Any]
    alert: dict[str, Any] | None = None
    log_callback: Any = None  # parent-side hook for log mirroring; optional
    integrations: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal: handle one IPC message from the child.  Each ``op`` returns a
# response payload that the caller writes back on the wire keyed by ``id``.
# ---------------------------------------------------------------------------


async def _handle_http_request(
    msg: dict[str, Any], http: httpx.AsyncClient
) -> dict[str, Any]:
    from app.services.url_validation import is_safe_outbound_url

    url = str(msg.get("url") or "")
    method = str(msg.get("method") or "GET").upper()
    safe, reason = is_safe_outbound_url(url)
    if not safe:
        return {
            "ok": False,
            "error_code": "ssrf_blocked",
            "message": reason or "URL blocked by SSRF protection",
        }

    headers = msg.get("headers") or {}
    params = msg.get("params") or {}
    body = msg.get("body")
    timeout = float(msg.get("timeout_seconds") or 30.0)

    request_kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "timeout": timeout,
    }
    if body is not None:
        request_kwargs["content"] = body.encode("utf-8") if isinstance(body, str) else body

    try:
        response = await http.request(**request_kwargs)
    except httpx.TimeoutException as exc:
        return {
            "ok": False,
            "error_code": "http_timeout",
            "message": str(exc),
        }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "error_code": "http_error",
            "message": str(exc),
        }

    return {
        "ok": True,
        "value": {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        },
    }


async def _handle_secret_get(
    msg: dict[str, Any],
    *,
    allowed_secrets: list[str],
) -> dict[str, Any]:
    """Resolve a secret on behalf of the child.

    S3 enforces two gates BEFORE reading os.environ:
      1. Global denylist — keys matching any sensitive pattern (CALSETA_*,
         *_API_KEY, DATABASE_URL, ENCRYPTION_KEY, AWS_*, AZURE_*, etc.) are
         never resolved, even if on the workflow's allowlist.
      2. Per-workflow allowlist — only names declared in
         ``workflow.allowed_secrets`` are resolved.

    A blocked or absent secret returns ``value: None`` (NOT an error envelope)
    so workflows that probe for an optional secret don't crash.
    """
    from app.secrets.denylist import is_denied

    name = str(msg.get("name") or "")
    if not name:
        return {"ok": True, "value": None}
    if is_denied(name):
        return {"ok": True, "value": None}
    if name not in allowed_secrets:
        return {"ok": True, "value": None}
    value = os.environ.get(name)
    return {"ok": True, "value": value}


def _handle_log(msg: dict[str, Any], log_buffer: list[dict[str, Any]]) -> dict[str, Any]:
    entry = {
        "level": str(msg.get("level") or "info"),
        "message": str(msg.get("message") or ""),
        "fields": dict(msg.get("fields") or {}),
    }
    log_buffer.append(entry)
    logger.debug(
        "workflow_subprocess_log",
        level=entry["level"],
        message=entry["message"],
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# IPC loop — pumped until either ``done`` arrives or the child exits.  Wall
# timeout is enforced by the caller wrapping this coroutine in wait_for.
# ---------------------------------------------------------------------------


async def _ipc_loop(
    proc: asyncio.subprocess.Process,
    http: httpx.AsyncClient,
    log_buffer: list[dict[str, Any]],
    *,
    allowed_secrets: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Run the IPC loop until ``done`` or pipe close.

    Returns ``(result_payload, metadata)`` where ``result_payload`` is the
    raw ``result`` dict from the child's ``done`` message, or ``None`` if
    the child closed without sending one.
    """
    assert proc.stdout is not None
    assert proc.stdin is not None

    total_bytes = 0
    final_result: dict[str, Any] | None = None
    final_metadata: dict[str, Any] | None = None

    while True:
        line = await proc.stdout.readline()
        if not line:
            return final_result, final_metadata
        total_bytes += len(line)
        if total_bytes > MAX_CHILD_OUTPUT_BYTES:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            raise RuntimeError("workflow child stdout exceeded cap")

        try:
            msg = json.loads(line.decode("utf-8").rstrip("\n"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Stray non-JSON line — skip but don't crash.
            continue
        if not isinstance(msg, dict):
            continue

        op = msg.get("op")

        if op == "done":
            result = msg.get("result")
            if isinstance(result, dict):
                final_result = result
            metadata = msg.get("metadata")
            if isinstance(metadata, dict):
                final_metadata = metadata
            return final_result, final_metadata

        # All other ops are requests that need a response keyed by id.
        msg_id = msg.get("id")
        if not isinstance(msg_id, str):
            continue

        try:
            if op == "http.request":
                response = await _handle_http_request(msg, http)
            elif op == "secret.get":
                response = await _handle_secret_get(msg, allowed_secrets=allowed_secrets)
            elif op == "log":
                response = _handle_log(msg, log_buffer)
            else:
                response = {
                    "ok": False,
                    "error_code": "ipc_protocol_error",
                    "message": f"unknown op: {op}",
                }
        except Exception as exc:  # noqa: BLE001
            response = {
                "ok": False,
                "error_code": "internal_error",
                "message": str(exc),
            }

        response["id"] = msg_id
        try:
            proc.stdin.write((json.dumps(response, default=str) + "\n").encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            return final_result, final_metadata


# ---------------------------------------------------------------------------
# Entry point: spawn child, run IPC loop, enforce timeout, clean up.
# ---------------------------------------------------------------------------


async def run_workflow_isolated(
    code: str,
    ctx_payload: dict[str, Any],
    *,
    timeout_seconds: int,
    memory_mb: int = 256,
    http_client: httpx.AsyncClient | None = None,
) -> WorkflowResult:
    """Execute a workflow in an isolated subprocess.

    Args:
        code:               Workflow source code (full module body).
        ctx_payload:        Plain-dict serializable view of the workflow's
                            context — keys: ``indicator`` (required),
                            ``alert`` (optional dict).
        timeout_seconds:    Wall-clock cap on child execution.
        memory_mb:          ``WORKFLOW_MAX_MEMORY_MB`` — wired to RLIMIT_AS.
        http_client:        Optional httpx.AsyncClient to use for proxied
                            requests; if None, a dedicated client is created.

    Returns ``WorkflowResult``; never raises.  Failures are mapped to
    ``WorkflowResult.fail(reason=...)``.
    """
    run_uuid = str(uuid4())

    # Per-run scratch directory.  Created by the parent, removed in
    # ``finally``.  The child cwd's into here, and any filesystem write the
    # child attempts is bounded to it (rlimit + lack of chdir on the seccomp
    # allowlist).
    workspace = os.path.join(tempfile.gettempdir(), f"workflow-{run_uuid}")
    os.makedirs(workspace, exist_ok=True)

    # Emit the seccomp warning once if we're on a platform without it.
    if not seccomp_available():
        _emit_seccomp_warning_once()

    # Scrubbed env — only the explicit allowlist plus PYTHONPATH so the
    # child can import ``app.*`` from the repo.
    parent_env = os.environ
    child_env: dict[str, str] = {}
    for var in _ALLOWED_CHILD_ENV_VARS:
        if parent_env.get(var):
            child_env[var] = parent_env[var]
    # PYTHONPATH lets the child resolve ``app.*`` regardless of cwd.
    # __file__ is app/workflows/runner.py — repo root is two levels up.
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    existing_pp = parent_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{existing_pp}" if existing_pp else repo_root
    )

    init_message = {
        "op": "init",
        "code": code,
        "run_uuid": run_uuid,
        "indicator": ctx_payload.get("indicator") or {},
        "alert": ctx_payload.get("alert"),
        "timeout_seconds": int(timeout_seconds),
        "memory_mb": int(memory_mb),
        "ipc_protocol_version": IPC_PROTOCOL_VERSION,
    }

    log_buffer: list[dict[str, Any]] = []
    own_http = http_client is None
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=float(timeout_seconds))

    proc: asyncio.subprocess.Process | None = None
    stderr_bytes = b""
    final_result: dict[str, Any] | None = None
    final_metadata: dict[str, Any] | None = None
    failure_reason: str | None = None

    # Resolve the absolute path to the entry script.  Invoking by absolute
    # path (rather than ``-m scripts.workflow_subprocess_entry``) avoids
    # depending on ``scripts/`` being a Python package and works regardless
    # of cwd.
    entry_script = os.path.join(repo_root, "scripts", "workflow_subprocess_entry.py")

    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                entry_script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
                cwd=workspace,
            )
        except FileNotFoundError as exc:
            return WorkflowResult.fail(
                f"workflow runtime not available: {exc}",
                {"reason": "child_crashed"},
            )

        # Send init line.
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(init_message) + "\n").encode("utf-8"))
        await proc.stdin.drain()

        # Wall-clock timeout: cap the IPC loop.  CPU and memory limits are
        # enforced by the child via rlimit.
        try:
            allowed_secrets_list: list[str] = [
                str(s) for s in (ctx_payload.get("allowed_secrets") or []) if s
            ]
            final_result, final_metadata = await asyncio.wait_for(
                _ipc_loop(
                    proc,
                    http_client,
                    log_buffer,
                    allowed_secrets=allowed_secrets_list,
                ),
                timeout=float(timeout_seconds) + 5.0,  # +5s for child startup
            )
        except TimeoutError:
            failure_reason = "timeout"
        except RuntimeError as exc:
            # Output cap exceeded — child already killed.
            failure_reason = "resource_limit_exceeded"
            logger.warning("workflow_isolated_output_cap", error=str(exc))

        # Drain stderr and reap the child.
        if proc is not None:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    with contextlib.suppress(Exception):
                        await proc.wait()
            try:
                if proc.stderr is not None:
                    stderr_bytes = await proc.stderr.read()
            except Exception:
                stderr_bytes = b""

    finally:
        if own_http:
            with contextlib.suppress(Exception):
                await http_client.aclose()
        with contextlib.suppress(Exception):
            shutil.rmtree(workspace, ignore_errors=True)

    # Map outcomes to WorkflowResult.
    stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
    rendered_log = _render_log_buffer(log_buffer)

    if failure_reason == "timeout":
        return WorkflowResult.fail(
            f"Workflow execution timed out after {timeout_seconds} seconds",
            {
                "reason": "timeout",
                "log_output": rendered_log,
                "stderr_tail": stderr_text[-2000:],
            },
        )
    if failure_reason == "resource_limit_exceeded":
        return WorkflowResult.fail(
            "Workflow exceeded resource cap (output bytes)",
            {
                "reason": "resource_limit_exceeded",
                "log_output": rendered_log,
                "stderr_tail": stderr_text[-2000:],
            },
        )

    returncode = proc.returncode if proc is not None else None

    if final_result is None:
        # Child exited without sending ``done``.  Map to either
        # ``resource_limit_exceeded`` (rlimit-killed by the kernel) or
        # ``child_crashed`` (anything else).
        is_resource_kill = _looks_like_resource_kill(returncode, stderr_text)
        reason = "resource_limit_exceeded" if is_resource_kill else "child_crashed"
        message = (
            "Workflow child process exited before completing"
            if reason == "child_crashed"
            else "Workflow child killed by resource limit"
        )
        return WorkflowResult.fail(
            f"{message} (returncode={returncode})",
            {
                "reason": reason,
                "returncode": returncode,
                "log_output": rendered_log,
                "stderr_tail": stderr_text[-2000:],
            },
        )

    # Happy path — child reported a result.  Annotate with metadata so the
    # caller can surface ``seccomp`` posture if needed.
    success = bool(final_result.get("success"))
    message = str(final_result.get("message", ""))
    data = dict(final_result.get("data") or {})
    if final_metadata:
        data["__metadata"] = final_metadata
    if rendered_log:
        data.setdefault("__log_buffer", rendered_log)
    return WorkflowResult(success=success, message=message, data=data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_log_buffer(buf: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(e, default=str) for e in buf)


def _looks_like_resource_kill(returncode: int | None, stderr_text: str) -> bool:
    """Heuristic: a child killed by rlimit/seccomp shows up as a negative
    returncode (signal) or as MemoryError on stderr."""
    if returncode is not None and returncode < 0:
        # POSIX: returncode == -SIGNAL when the child died from a signal.
        return True
    # Python prints ``MemoryError`` to stderr when RLIMIT_AS bites during alloc.
    return "MemoryError" in stderr_text or "Killed" in stderr_text


def serialize_indicator(indicator_ctx: Any) -> dict[str, Any]:
    """Convert ``IndicatorContext`` to a JSON-safe dict for the init payload."""
    return {
        "uuid": str(indicator_ctx.uuid),
        "type": indicator_ctx.type,
        "value": indicator_ctx.value,
        "malice": indicator_ctx.malice,
        "is_enriched": indicator_ctx.is_enriched,
        "enrichment_results": indicator_ctx.enrichment_results,
        "first_seen": indicator_ctx.first_seen.isoformat() if indicator_ctx.first_seen else None,
        "last_seen": indicator_ctx.last_seen.isoformat() if indicator_ctx.last_seen else None,
        "created_at": indicator_ctx.created_at.isoformat() if indicator_ctx.created_at else None,
        "updated_at": indicator_ctx.updated_at.isoformat() if indicator_ctx.updated_at else None,
    }


def serialize_alert(alert_ctx: Any) -> dict[str, Any] | None:
    if alert_ctx is None:
        return None
    return {
        "uuid": str(alert_ctx.uuid),
        "title": alert_ctx.title,
        "severity": alert_ctx.severity,
        "source_name": alert_ctx.source_name,
        "status": alert_ctx.status,
        "occurred_at": alert_ctx.occurred_at.isoformat() if alert_ctx.occurred_at else None,
        "tags": list(alert_ctx.tags or []),
        "raw_payload": dict(alert_ctx.raw_payload or {}),
    }
