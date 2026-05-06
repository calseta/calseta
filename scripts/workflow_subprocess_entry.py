"""
Workflow subprocess entry point (Wave 5 / S1).

This script is the ``child`` half of the workflow process-isolation runtime.
The parent (``app/workflows/runner.py``) spawns this script as a separate OS
process using ``asyncio.create_subprocess_exec`` and communicates with it via
NDJSON over stdin/stdout. One JSON object per line, in each direction.

Lifecycle (child side):

    1. Receive an ``init`` message on stdin describing the run:
        { "op": "init",
          "code": "<workflow source>",
          "run_uuid": "<uuid>",
          "indicator": {...},
          "alert": {...} | null,
          "timeout_seconds": int,
          "memory_mb": int,
          "ipc_protocol_version": "1" }
    2. Install ``prctl(PR_SET_NO_NEW_PRIVS)`` + seccomp-bpf filter (Linux only,
       when ``pyseccomp`` is importable).  On other platforms the child runs
       with rlimits only.
    3. Build a ``WorkflowContext`` whose ``http`` / ``secrets`` / ``log``
       primitives are IPC proxies — every call writes a request line on
       stdout and awaits the matching response on stdin.
    4. Compile the workflow code in the existing AST-allowlisted sandbox and
       run it.  When ``run`` returns, send a final ``done`` line and exit 0.

The workflow body runs on a worker thread with its own asyncio event loop;
the IPC broker runs on the main thread's loop.  This split lets the workflow
expose sync APIs (``ctx.secrets.get(...)``) while still routing them through
the parent — the worker-thread call uses ``run_coroutine_threadsafe`` to
hand off to the broker loop without deadlocking either side.

The child has NO direct database, network, or filesystem access to anything
outside its tmpdir.  All capability is mediated by the parent.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import resource as _resource
import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

# ---------------------------------------------------------------------------
# IPC protocol version — bumped if the wire format changes incompatibly.
# ---------------------------------------------------------------------------

IPC_PROTOCOL_VERSION = "1"


# ---------------------------------------------------------------------------
# Bootstrap path.  The parent invokes the child as
# ``python -m scripts.workflow_subprocess_entry`` from the repo root, so
# ``app.*`` is already importable.  When running this file directly for
# debugging, prepend the repo root.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Conditional libseccomp import.  Linux + libseccomp installed → real filter;
# anywhere else → rlimit-only and the parent will have already emitted the
# ``workflow.seccomp_unavailable`` event.
# ---------------------------------------------------------------------------

try:
    import pyseccomp as _seccomp  # type: ignore[import-not-found]

    SECCOMP_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on host
    _seccomp = None  # type: ignore[assignment]
    SECCOMP_AVAILABLE = False


# ---------------------------------------------------------------------------
# Allowed syscalls — locked allowlist from the design.  Matters only on Linux.
# ---------------------------------------------------------------------------

_ALLOWED_SYSCALLS: tuple[str, ...] = (
    # Time / signals / process-self
    "clock_gettime",
    "clock_nanosleep",
    "nanosleep",
    "gettimeofday",
    "rt_sigaction",
    "rt_sigprocmask",
    "rt_sigreturn",
    "getpid",
    "gettid",
    "tgkill",
    "exit",
    "exit_group",
    "futex",
    "sched_yield",
    "set_robust_list",
    "get_robust_list",
    # Memory
    "mmap",
    "munmap",
    "mprotect",
    "brk",
    "madvise",
    # FDs (already-open) — pipes for IPC, plus stdlib internals
    "read",
    "write",
    "readv",
    "writev",
    "close",
    "fstat",
    "lseek",
    "pread64",
    "pwrite64",
    "dup",
    "dup2",
    "fcntl",
    "poll",
    "ppoll",
    "select",
    "pselect6",
    "epoll_create1",
    "epoll_ctl",
    "epoll_wait",
    "epoll_pwait",
    "eventfd2",
    "pipe",
    "pipe2",
    # File ops; path enforcement comes from cwd, not from the filter.
    "openat",
    "newfstatat",
    "stat",
    "lstat",
    "getdents64",
    "unlinkat",
    "mkdirat",
    "readlink",
    "readlinkat",
    "getcwd",
    # Network — child needs these for the NDJSON pipe to function (asyncio
    # event loop manages internal sockets); SSRF gating runs in the parent.
    "socket",
    "connect",
    "bind",
    "listen",
    "accept4",
    "sendto",
    "recvfrom",
    "sendmsg",
    "recvmsg",
    "shutdown",
    "getsockname",
    "getpeername",
    "getsockopt",
    "setsockopt",
    # Threading + low-level (CPython needs CLONE_THREAD).  ``execve`` is what
    # the threat model cares about and that is denied (not on the list).
    "clone",
    "clone3",
    "rseq",
    "prlimit64",
    "getrandom",
    "uname",
    "arch_prctl",
    "set_tid_address",
)


def _install_seccomp_filter() -> bool:
    """Install a seccomp-bpf filter that KILLs on syscalls outside the allowlist.

    Returns True if the filter was installed, False if pyseccomp is not
    available on this platform.
    """
    if not SECCOMP_AVAILABLE or _seccomp is None:
        return False

    # PR_SET_NO_NEW_PRIVS = 38 is required by the kernel for unprivileged
    # processes installing a filter.
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
        libc.prctl(38, 1, 0, 0, 0)
    except Exception:  # pragma: no cover - fail open is safer than dying here
        pass

    f = _seccomp.SyscallFilter(defaction=_seccomp.KILL_PROCESS)
    for name in _ALLOWED_SYSCALLS:
        try:
            f.add_rule(_seccomp.ALLOW, name)
        except Exception:
            # Some syscalls don't exist on every libseccomp version — skip.
            continue
    f.load()
    return True


# ---------------------------------------------------------------------------
# rlimits — wall time is enforced by the parent via asyncio.wait_for; CPU and
# memory ceilings are enforced here so a runaway workflow gets killed by the
# kernel even if the parent stalls.
# ---------------------------------------------------------------------------


def _install_rlimits(memory_mb: int, cpu_seconds: int) -> None:
    max_bytes = memory_mb * 1024 * 1024
    for limit_attr in ("RLIMIT_AS", "RLIMIT_RSS"):
        rlimit = getattr(_resource, limit_attr, None)
        if rlimit is None:
            continue
        try:
            soft, hard = _resource.getrlimit(rlimit)
            effective = (
                min(max_bytes, hard) if hard != _resource.RLIM_INFINITY else max_bytes
            )
            _resource.setrlimit(rlimit, (effective, hard))
            break
        except (ValueError, OSError):
            continue

    rlimit_cpu = getattr(_resource, "RLIMIT_CPU", None)
    if rlimit_cpu is not None and cpu_seconds > 0:
        try:
            soft, hard = _resource.getrlimit(rlimit_cpu)
            effective = (
                min(cpu_seconds, hard) if hard != _resource.RLIM_INFINITY else cpu_seconds
            )
            _resource.setrlimit(rlimit_cpu, (effective, hard))
        except (ValueError, OSError):
            pass


# ---------------------------------------------------------------------------
# IPC primitives — read/write a JSON line on stdin/stdout.  stdout is the IPC
# channel and MUST stay free of stray prints.  Diagnostics from the child go
# to stderr; the parent forwards them only at debug level.
# ---------------------------------------------------------------------------


async def _write_line(stream: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    line = (json.dumps(payload, default=str) + "\n").encode("utf-8")
    stream.write(line)
    await stream.drain()


async def _read_line(stream: asyncio.StreamReader) -> dict[str, Any] | None:
    raw = await stream.readline()
    if not raw:
        return None
    try:
        result = json.loads(raw.decode("utf-8").rstrip("\n"))
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# IPC broker — runs on the main asyncio loop, serializes outgoing requests on
# stdout, dispatches incoming responses by id.
# ---------------------------------------------------------------------------


@dataclass
class _PendingResponse:
    future: asyncio.Future[dict[str, Any]]


class _IPCBroker:
    def __init__(
        self, stdin: asyncio.StreamReader, stdout: asyncio.StreamWriter
    ) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._pending: dict[str, _PendingResponse] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._write_lock = asyncio.Lock()

    def start(self) -> None:
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task

    async def _reader_loop(self) -> None:
        while not self._closed:
            msg = await _read_line(self._stdin)
            if msg is None:
                # Parent closed the pipe — fail every pending request.
                for pending in self._pending.values():
                    if not pending.future.done():
                        pending.future.set_result(
                            {"ok": False, "error_code": "ipc_closed"}
                        )
                self._pending.clear()
                break
            msg_id = msg.get("id")
            if not isinstance(msg_id, str):
                continue
            pending = self._pending.pop(msg_id, None)  # type: ignore[arg-type]
            if pending is None:
                continue
            if not pending.future.done():
                pending.future.set_result(msg)

    async def request(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._closed:
            return {"ok": False, "error_code": "ipc_closed"}
        req_id = str(uuid4())
        message = {"id": req_id, "op": op, **payload}
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = _PendingResponse(future=future)
        async with self._write_lock:
            await _write_line(self._stdout, message)
        try:
            return await future
        finally:
            self._pending.pop(req_id, None)


# ---------------------------------------------------------------------------
# Bridge from the workflow's worker thread to the broker's loop thread.
# The broker lives on the ``main`` loop; the workflow's ``async def run`` is
# scheduled on a ``worker`` loop running in a separate thread.  Sync calls
# from inside the workflow (e.g. ``ctx.secrets.get``) call ``broker_call``
# which uses ``run_coroutine_threadsafe`` to hand the request to the broker
# loop without blocking either loop.
# ---------------------------------------------------------------------------


class _BrokerBridge:
    def __init__(
        self, broker: _IPCBroker, broker_loop: asyncio.AbstractEventLoop
    ) -> None:
        self._broker = broker
        self._broker_loop = broker_loop

    def call_sync(
        self, op: str, payload: dict[str, Any], *, timeout: float = 60.0
    ) -> dict[str, Any]:
        future = asyncio.run_coroutine_threadsafe(
            self._broker.request(op, payload), self._broker_loop
        )
        try:
            return future.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error_code": "ipc_timeout", "message": str(exc)}

    async def call_async(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Called from the worker loop; still hand off to the broker loop.
        future = asyncio.run_coroutine_threadsafe(
            self._broker.request(op, payload), self._broker_loop
        )
        # Wrap concurrent.futures.Future into asyncio.Future for this loop.
        return await asyncio.wrap_future(future)


# ---------------------------------------------------------------------------
# IPC proxy classes (mirror the WorkflowContext public surface).
# ---------------------------------------------------------------------------


class WorkflowIPCError(Exception):
    """Raised by IPC proxies when the parent rejects a request (e.g. SSRF)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class _IPCResponse:
    status_code: int
    headers: dict[str, str]
    text: str
    url: str

    def json(self) -> Any:
        return json.loads(self.text) if self.text else None

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            raise WorkflowIPCError(
                "http_status_error",
                f"HTTP {self.status_code} for {self.url}",
            )


class _IPCHttpClient:
    """Stand-in for ``httpx.AsyncClient``.

    Workflows use ``ctx.http.get(url)`` / ``post`` / ``request`` etc.  Each
    call serializes to an ``http.request`` IPC op and parses the parent's
    response into an ``_IPCResponse`` mimicking ``httpx.Response``.
    """

    def __init__(self, bridge: _BrokerBridge, default_timeout: float) -> None:
        self._bridge = bridge
        self._default_timeout = default_timeout

    async def __aenter__(self) -> _IPCHttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        content: Any = None,
        timeout: float | None = None,
        **_kwargs: Any,
    ) -> _IPCResponse:
        body: str | None = None
        if json is not None:
            import json as _stdjson

            body = _stdjson.dumps(json)
            headers = dict(headers or {})
            headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            body = str(data) if not isinstance(data, str) else data
        elif content is not None:
            if isinstance(content, bytes):
                body = content.decode("utf-8", errors="replace")
            else:
                body = str(content)

        payload = {
            "method": method.upper(),
            "url": url,
            "headers": dict(headers or {}),
            "params": dict(params or {}),
            "body": body,
            "timeout_seconds": float(timeout) if timeout is not None else self._default_timeout,
        }
        response = await self._bridge.call_async("http.request", payload)
        if not response.get("ok"):
            error_code = response.get("error_code", "http_error")
            raise WorkflowIPCError(error_code, response.get("message", error_code))
        value = response.get("value", {})
        return _IPCResponse(
            status_code=int(value.get("status", 0)),
            headers=dict(value.get("headers") or {}),
            text=str(value.get("body") or ""),
            url=url,
        )

    async def get(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("DELETE", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> _IPCResponse:
        return await self.request("HEAD", url, **kwargs)


class _IPCSecretsAccessor:
    """Mirrors ``SecretsAccessor`` but routes ``get`` through the parent.

    ``get`` is synchronous (matching the public contract); the bridge
    handles the cross-thread hop to the broker loop.
    """

    def __init__(self, bridge: _BrokerBridge) -> None:
        self._bridge = bridge
        self._cache: dict[str, str | None] = {}

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        response = self._bridge.call_sync("secret.get", {"name": key})
        if not response.get("ok"):
            self._cache[key] = None
            return None
        value = response.get("value")
        result = value if isinstance(value, str) else None
        self._cache[key] = result
        return result


class _IPCWorkflowLogger:
    """Mirrors ``WorkflowLogger`` and forwards entries to the parent.

    The local in-memory buffer is preserved (workflow code may inspect it via
    ``log.render``), and each entry is also forwarded to the parent so the
    full log shows up in the parent's run audit alongside any redaction.
    """

    def __init__(self, bridge: _BrokerBridge) -> None:
        self._bridge = bridge
        self._entries: list[dict[str, Any]] = []

    def _append(self, level: str, message: str, **kwargs: Any) -> None:
        from datetime import UTC

        entry: dict[str, Any] = {
            "level": level,
            "message": message,
            "ts": datetime.now(UTC).isoformat(),
        }
        if kwargs:
            entry["extra"] = kwargs
        self._entries.append(entry)
        # Fire-and-forget — log entries should not stall workflow execution.
        # call_sync with a tight timeout, errors swallowed.
        with contextlib.suppress(Exception):
            self._bridge.call_sync(
                "log",
                {"level": level, "message": message, "fields": kwargs},
                timeout=2.0,
            )

    def __call__(self, message: str, **kwargs: Any) -> None:
        self._append("info", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._append("info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._append("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._append("error", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._append("debug", message, **kwargs)

    def render(self) -> str:
        return "\n".join(json.dumps(e, default=str) for e in self._entries)


# ---------------------------------------------------------------------------
# Context construction from the init payload
# ---------------------------------------------------------------------------


def _build_workflow_context(init: dict[str, Any], bridge: _BrokerBridge) -> Any:
    from app.workflows.context import (
        AlertContext,
        IndicatorContext,
        IntegrationClients,
        WorkflowContext,
    )

    ind = init.get("indicator") or {}
    indicator = IndicatorContext(
        uuid=UUID(ind["uuid"]) if ind.get("uuid") else uuid4(),
        type=str(ind.get("type", "")),
        value=str(ind.get("value", "")),
        malice=str(ind.get("malice", "Pending")),
        is_enriched=bool(ind.get("is_enriched", False)),
        enrichment_results=ind.get("enrichment_results"),
        first_seen=_parse_dt(ind.get("first_seen")),
        last_seen=_parse_dt(ind.get("last_seen")),
        created_at=_parse_dt(ind.get("created_at")),
        updated_at=_parse_dt(ind.get("updated_at")),
    )

    alert: AlertContext | None = None
    alert_payload = init.get("alert")
    if alert_payload:
        alert = AlertContext(
            uuid=UUID(alert_payload["uuid"]) if alert_payload.get("uuid") else uuid4(),
            title=str(alert_payload.get("title", "")),
            severity=str(alert_payload.get("severity", "")),
            source_name=str(alert_payload.get("source_name", "")),
            status=str(alert_payload.get("status", "")),
            occurred_at=_parse_dt(alert_payload.get("occurred_at")),
            tags=list(alert_payload.get("tags") or []),
            raw_payload=dict(alert_payload.get("raw_payload") or {}),
        )

    timeout = float(init.get("timeout_seconds", 30) or 30)
    http_client = _IPCHttpClient(bridge, default_timeout=timeout)
    secrets = _IPCSecretsAccessor(bridge)
    logger = _IPCWorkflowLogger(bridge)

    return WorkflowContext(
        indicator=indicator,
        alert=alert,
        http=http_client,  # type: ignore[arg-type]
        log=logger,  # type: ignore[arg-type]
        secrets=secrets,  # type: ignore[arg-type]
        integrations=IntegrationClients(),
    )


def _parse_dt(value: Any) -> datetime:
    from datetime import UTC

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Worker thread — runs the workflow on its own asyncio loop so the broker on
# the main thread stays responsive during the workflow's awaits.
# ---------------------------------------------------------------------------


def _worker_thread_run(
    code: str,
    init: dict[str, Any],
    bridge: _BrokerBridge,
    timeout_seconds: int,
    memory_mb: int,
    result_holder: dict[str, Any],
) -> None:
    """Worker thread entry; populates ``result_holder`` with a final payload."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run_inner() -> dict[str, Any]:
        from app.workflows.sandbox import run_workflow_code

        ctx = _build_workflow_context(init, bridge)
        result = await run_workflow_code(
            code=code,
            ctx=ctx,
            timeout=timeout_seconds,
            max_memory_mb=memory_mb,
        )
        return {
            "success": bool(result.success),
            "message": str(result.message),
            "data": dict(result.data or {}),
        }

    try:
        result_holder["payload"] = loop.run_until_complete(_run_inner())
    except Exception as exc:  # noqa: BLE001
        result_holder["payload"] = {
            "success": False,
            "message": f"child_exception: {exc}",
            "data": {"traceback": traceback.format_exc()[-2000:]},
        }
    finally:
        with contextlib.suppress(Exception):
            loop.close()


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


async def _read_init(stdin: asyncio.StreamReader) -> dict[str, Any]:
    msg = await _read_line(stdin)
    if msg is None or msg.get("op") != "init":
        raise RuntimeError("expected init message on stdin")
    return msg


async def _async_main() -> int:
    loop = asyncio.get_running_loop()

    # Wire up async streams over inherited stdio.
    stdin_reader = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(stdin_reader), sys.stdin
    )
    stdout_transport, stdout_proto = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    stdout_writer = asyncio.StreamWriter(stdout_transport, stdout_proto, None, loop)

    # Block 1 — receive init.
    try:
        init = await _read_init(stdin_reader)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"workflow_subprocess_init_failed: {exc}\n")
        return 2

    memory_mb = int(init.get("memory_mb") or 256)
    timeout_seconds = int(init.get("timeout_seconds") or 30)
    cpu_seconds = int(init.get("cpu_seconds") or max(timeout_seconds * 2, 5))

    # Block 2 — install confinement.  rlimits first; seccomp last (after
    # stdlib has been touched) since it's the strictest filter.
    _install_rlimits(memory_mb=memory_mb, cpu_seconds=cpu_seconds)

    # Pre-import everything the workflow may need so the seccomp filter
    # doesn't block module loading.
    import importlib

    for module_name in (
        "json",
        "asyncio",
        "datetime",
        "urllib.parse",
        "uuid",
        "concurrent.futures",
        "app.workflows.context",
        "app.workflows.sandbox",
    ):
        with contextlib.suppress(Exception):
            importlib.import_module(module_name)

    seccomp_installed = False
    if SECCOMP_AVAILABLE:
        try:
            seccomp_installed = _install_seccomp_filter()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"seccomp_install_failed: {exc}\n")
            seccomp_installed = False

    # Block 3 — broker on this loop, workflow on a worker thread.
    broker = _IPCBroker(stdin_reader, stdout_writer)
    broker.start()
    bridge = _BrokerBridge(broker, loop)

    result_holder: dict[str, Any] = {
        "payload": {"success": False, "message": "no_result", "data": {}}
    }

    code = str(init.get("code") or "")
    worker = threading.Thread(
        target=_worker_thread_run,
        args=(code, init, bridge, timeout_seconds, memory_mb, result_holder),
        name="workflow-worker",
        daemon=True,
    )
    worker.start()

    # Wait for the worker on the broker loop without blocking — yield to let
    # the broker service IPC requests from the workflow.
    while worker.is_alive():
        await asyncio.sleep(0.05)
    # Final join in case the thread ended between iterations.
    worker.join(timeout=1.0)

    result_payload = result_holder.get("payload") or {
        "success": False,
        "message": "missing_result",
        "data": {},
    }

    # Block 4 — emit the final ``done`` line and shut down the broker.
    with contextlib.suppress(Exception):
        await _write_line(
            stdout_writer,
            {
                "id": str(uuid4()),
                "op": "done",
                "result": result_payload,
                "metadata": {
                    "seccomp": seccomp_installed,
                    "ipc_protocol_version": IPC_PROTOCOL_VERSION,
                },
            },
        )

    await broker.stop()
    return 0


def main() -> None:
    try:
        rc = asyncio.run(_async_main())
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"workflow_subprocess_fatal: {exc}\n")
        rc = 3
    sys.exit(rc)


if __name__ == "__main__":
    main()
