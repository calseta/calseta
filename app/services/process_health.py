"""Cross-platform PID + start-time liveness checks for orphan detection.

Why start time matters
----------------------
A bare ``os.kill(pid, 0)`` probe answers "does *some* process with this PID
exist right now?" That is not the same question the supervisor needs to ask,
which is "is the *original* process I spawned still alive?". Operating systems
recycle PIDs aggressively — within minutes on a busy host. If the worker that
owned ``pid=12345`` died and the kernel handed ``12345`` to an unrelated
``cron`` job before the supervisor ran, ``os.kill`` would happily report
"alive" and we would never detect the orphan.

The defense is to compare the process's recorded *start time* against the
start time stored in the HeartbeatRun row when the subprocess was originally
spawned (chunk A3 populates ``process_started_at``). Same PID + same start
time within a small tolerance = same process. Same PID + different start
time = PID was recycled and the original process is dead.

Linux:    parse field 22 of ``/proc/<pid>/stat`` (start time in clock ticks
          since boot), convert to UTC datetime via boot time + ``SC_CLK_TCK``.
macOS:    no procfs; fall back to ``psutil`` if available, else log a
          structured warning and assume DEAD (the safer default — false-
          positive-orphan is recoverable, missed-orphan is not).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Tolerance window for matching recorded vs observed start time. Linux records
# start time in clock ticks (typically 100Hz = 10ms granularity); the recorded
# value comes from ``datetime.now(UTC)`` taken in the parent process before
# fork/exec. A couple of seconds covers clock drift, scheduling jitter, and
# the fork-to-record gap.
_START_TIME_TOLERANCE = timedelta(seconds=2)


def is_process_alive(
    pid: int,
    recorded_started_at: datetime | None,
) -> bool:
    """Return True if the process at ``pid`` is the same one we spawned.

    Parameters
    ----------
    pid:
        The OS process ID to probe.
    recorded_started_at:
        The wall-clock time the subprocess was launched, as captured by the
        engine when it called ``Popen`` (HeartbeatRun.process_started_at).
        If ``None``, fall back to a plain liveness probe — used by callers
        that have not yet recorded a start time.

    Returns
    -------
    bool
        ``True`` if the PID is alive and (when start time is supplied) its
        observed start time matches ``recorded_started_at`` within
        ±2 seconds. ``False`` for any of:

        * PID does not exist
        * PID exists but its observed start time does not match (PID reuse)
        * Start time cannot be verified on this platform and no liveness
          probe could confirm the process — assume DEAD (safer default)

    Never raises. All errors are logged and translated into a boolean.
    """
    if pid is None or pid <= 0:
        return False

    # Fast path: if the kernel tells us this PID has no process at all, it
    # cannot be the process we spawned — done.
    if not _pid_exists(pid):
        return False

    # No recorded start time → caller is doing a plain liveness probe. The
    # kernel said the PID exists, so report alive. This is the legacy B4
    # behaviour and is used by callers that have not yet adopted A3 fields.
    if recorded_started_at is None:
        return True

    observed = _read_process_start_time(pid)
    if observed is None:
        # Platform could not determine start time. Per the spec, prefer the
        # safer default: assume DEAD so the supervisor recovers the run.
        # macOS dev environments will hit this path when psutil is not
        # installed; CI on Linux is the authoritative correctness check.
        logger.warning(
            "process_health.starttime_unverifiable",
            pid=pid,
            recorded_started_at=recorded_started_at.isoformat(),
        )
        return False

    # Normalise both sides to aware UTC for comparison.
    if recorded_started_at.tzinfo is None:
        recorded_aware = recorded_started_at.replace(tzinfo=UTC)
    else:
        recorded_aware = recorded_started_at.astimezone(UTC)

    delta = abs(observed - recorded_aware)
    if delta <= _START_TIME_TOLERANCE:
        return True

    logger.warning(
        "process_health.pid_reuse_detected",
        pid=pid,
        recorded_started_at=recorded_aware.isoformat(),
        observed_started_at=observed.isoformat(),
        delta_seconds=delta.total_seconds(),
    )
    return False


def _pid_exists(pid: int) -> bool:
    """Return True if a process with this PID currently exists.

    Treats ``PermissionError`` as "exists" — the process is owned by another
    user but the kernel confirmed its existence by raising EPERM rather than
    ESRCH.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Any other OS-level failure (e.g. EINVAL) is treated as "we cannot
        # confirm liveness" — return False so the caller can take the safer
        # path (start-time check or assume dead).
        return False
    return True


def _read_process_start_time(pid: int) -> datetime | None:
    """Return the UTC datetime when ``pid`` was started, or None if unknown.

    Tries the Linux procfs path first, then falls back to ``psutil`` (which
    handles macOS, BSD, and Windows). Returns ``None`` on any failure.
    """
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            return _read_linux_start_time(pid)
        except (FileNotFoundError, ProcessLookupError):
            return None
        except (OSError, PermissionError, ValueError) as exc:
            logger.debug(
                "process_health.proc_stat_read_failed",
                pid=pid,
                error=str(exc),
            )
            # fall through to psutil

    return _read_start_time_via_psutil(pid)


def _read_linux_start_time(pid: int) -> datetime | None:
    """Parse ``/proc/<pid>/stat`` field 22 and convert to a UTC datetime.

    Field 22 (``starttime``) is the time the process started after system
    boot, in clock ticks. Converting to wall-clock time requires the boot
    time and ``SC_CLK_TCK``.
    """
    stat_path = Path(f"/proc/{pid}/stat")
    raw = stat_path.read_text()

    # Field 2 ("comm") is enclosed in parentheses and may contain spaces or
    # whitespace. Anchor on the *last* ')' so that everything after it is
    # space-separated and field-indexable.
    rparen = raw.rfind(")")
    if rparen == -1:
        return None
    rest = raw[rparen + 2 :].split()  # skip ") "
    # After the close paren, the next token is field 3 (state), so field N
    # is at index N - 3.
    if len(rest) < 22 - 2:
        return None
    starttime_ticks = int(rest[22 - 3])

    clk_tck = os.sysconf("SC_CLK_TCK")
    if clk_tck <= 0:
        return None
    seconds_since_boot = starttime_ticks / clk_tck

    boot_time_epoch = _read_linux_boot_time_epoch()
    if boot_time_epoch is None:
        return None

    return datetime.fromtimestamp(
        boot_time_epoch + seconds_since_boot, tz=UTC,
    )


def _read_linux_boot_time_epoch() -> float | None:
    """Return the system boot time as Unix epoch seconds (UTC).

    Tries ``psutil.boot_time()`` first if available (more precise, cached);
    falls back to deriving boot time from ``/proc/uptime``.
    """
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.boot_time())
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("process_health.psutil_boot_time_failed", error=str(exc))

    try:
        uptime_text = Path("/proc/uptime").read_text()
        uptime_seconds = float(uptime_text.split()[0])
    except (FileNotFoundError, OSError, ValueError):
        return None

    # Boot time = now - uptime. Use UTC throughout.
    now_epoch = datetime.now(UTC).timestamp()
    return now_epoch - uptime_seconds


def _read_start_time_via_psutil(pid: int) -> datetime | None:
    """Return process start time using psutil. Returns None if unavailable."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        proc = psutil.Process(pid)
        return datetime.fromtimestamp(proc.create_time(), tz=UTC)
    except Exception as exc:
        logger.debug(
            "process_health.psutil_create_time_failed",
            pid=pid,
            error=str(exc),
        )
        return None
