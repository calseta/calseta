"""Integration tests for ``app.services.process_health``.

These tests live in ``tests/integration/`` because they exercise real OS
state (live PIDs, ``/proc`` reads, subprocess spawn) rather than purely
mocked unit logic. They do not touch the database, so the conftest's
``db_session`` fixture is unused.

The PID-reuse scenario cannot be reproduced safely on a multi-tenant CI
host (we cannot force the kernel to recycle a specific PID), so it is
exercised by mocking ``_pid_exists`` + ``_read_process_start_time`` to
simulate the recycled-PID condition. Linux CI provides authoritative
coverage of the procfs parser via ``test_real_self_process_alive``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import process_health
from app.services.process_health import is_process_alive

# ---------------------------------------------------------------------------
# Liveness probe
# ---------------------------------------------------------------------------


def test_dead_pid_returns_false() -> None:
    """A PID that has never existed must be reported as dead."""
    # 2**31 - 1 is the max signed 32-bit int; on Linux PID_MAX is typically
    # 4 million. This PID will not exist on any reasonable host.
    assert is_process_alive(2**31 - 1, datetime.now(UTC)) is False


def test_zero_or_negative_pid_returns_false() -> None:
    """Defensive: bogus PIDs short-circuit to False without OS probing."""
    assert is_process_alive(0, datetime.now(UTC)) is False
    assert is_process_alive(-1, datetime.now(UTC)) is False


def test_none_recorded_started_at_falls_back_to_liveness() -> None:
    """Without a recorded start time, return whatever the kernel reports.

    This preserves backward compatibility with callers that have not yet
    populated ``process_started_at`` (legacy B4 behaviour).
    """
    assert is_process_alive(os.getpid(), None) is True
    assert is_process_alive(2**31 - 1, None) is False


# ---------------------------------------------------------------------------
# Linux: real procfs read against this test process
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path("/proc/self/stat").exists(),
    reason="Requires Linux procfs",
)
def test_real_self_process_alive_with_matching_start_time() -> None:
    """On Linux, reading our own PID's start time should round-trip cleanly.

    This is the authoritative correctness check for the ``/proc/<pid>/stat``
    parser. We compute our own observed start time, then ask
    ``is_process_alive`` to verify it — should always be True.
    """
    pid = os.getpid()
    observed = process_health._read_process_start_time(pid)
    assert observed is not None, "Linux procfs parser failed on self"

    # Feeding the observed value back in must register as alive.
    assert is_process_alive(pid, observed) is True


@pytest.mark.skipif(
    not Path("/proc/self/stat").exists(),
    reason="Requires Linux procfs",
)
def test_real_self_process_with_stale_start_time_returns_false() -> None:
    """Same PID + start time off by minutes = treat as PID reuse → DEAD."""
    pid = os.getpid()
    observed = process_health._read_process_start_time(pid)
    assert observed is not None

    stale = observed - timedelta(minutes=5)
    assert is_process_alive(pid, stale) is False


# ---------------------------------------------------------------------------
# PID reuse: simulated via mocking (cannot be reproduced safely on CI)
# ---------------------------------------------------------------------------


def test_pid_reuse_detected_when_start_time_mismatches() -> None:
    """Same PID reported alive but observed start time ≠ recorded → DEAD.

    Models the dangerous condition: original process died, kernel recycled
    its PID for an unrelated process, supervisor wakes up. Plain ``os.kill``
    would say "alive" — the start-time check must catch the impostor.
    """
    pid = 12345
    recorded = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    observed = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)  # 1h later

    with (
        patch.object(process_health, "_pid_exists", return_value=True),
        patch.object(
            process_health,
            "_read_process_start_time",
            return_value=observed,
        ),
    ):
        assert is_process_alive(pid, recorded) is False


def test_pid_match_within_tolerance_returns_alive() -> None:
    """Observed start time within ±2s of recorded → alive."""
    pid = 12345
    recorded = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    observed = recorded + timedelta(milliseconds=500)

    with (
        patch.object(process_health, "_pid_exists", return_value=True),
        patch.object(
            process_health,
            "_read_process_start_time",
            return_value=observed,
        ),
    ):
        assert is_process_alive(pid, recorded) is True


def test_pid_match_outside_tolerance_returns_dead() -> None:
    """Observed start time off by >2s → treated as PID reuse → DEAD."""
    pid = 12345
    recorded = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    observed = recorded + timedelta(seconds=5)

    with (
        patch.object(process_health, "_pid_exists", return_value=True),
        patch.object(
            process_health,
            "_read_process_start_time",
            return_value=observed,
        ),
    ):
        assert is_process_alive(pid, recorded) is False


def test_naive_recorded_datetime_treated_as_utc() -> None:
    """Naive ``recorded_started_at`` is normalised to UTC, not rejected."""
    pid = 12345
    observed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    naive_recorded = datetime(2026, 1, 1, 12, 0, 0)  # no tzinfo

    with (
        patch.object(process_health, "_pid_exists", return_value=True),
        patch.object(
            process_health,
            "_read_process_start_time",
            return_value=observed,
        ),
    ):
        assert is_process_alive(pid, naive_recorded) is True


# ---------------------------------------------------------------------------
# Unverifiable start time → assume DEAD (safer default)
# ---------------------------------------------------------------------------


def test_unverifiable_start_time_assumes_dead() -> None:
    """If platform cannot determine start time, prefer DEAD over MISSED."""
    pid = 12345
    recorded = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    with (
        patch.object(process_health, "_pid_exists", return_value=True),
        patch.object(
            process_health,
            "_read_process_start_time",
            return_value=None,
        ),
    ):
        assert is_process_alive(pid, recorded) is False


# ---------------------------------------------------------------------------
# End-to-end: real subprocess spawn + kill
# ---------------------------------------------------------------------------


def _start_time_observable() -> bool:
    """True if we can observe a real process's start time on this host.

    Linux procfs is always observable; otherwise we need ``psutil``. macOS
    dev hosts without psutil hit the "unverifiable → assume DEAD" path,
    which would fail the alive-assertion in the smoke test below.
    """
    if Path("/proc/self/stat").exists():
        return True
    try:
        import psutil  # noqa: F401  # type: ignore[import-not-found]
    except ImportError:
        return False
    return True


@pytest.mark.skipif(
    not _start_time_observable(),
    reason="No procfs and no psutil — start time cannot be observed",
)
def test_real_subprocess_alive_then_dead() -> None:
    """Spawn a sleeper, verify alive, kill it, verify dead.

    Cross-platform smoke test that the helper agrees with reality for an
    actual short-lived process. Does not exercise PID reuse (impossible to
    force on a real host) — that path is covered by the mocked tests above.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    recorded = datetime.now(UTC)

    try:
        # Brief delay so /proc/<pid>/stat is populated and start time is
        # stable. The tolerance window is 2s, so this is well within it.
        time.sleep(0.1)
        assert is_process_alive(proc.pid, recorded) is True

        proc.terminate()
        proc.wait(timeout=5)

        # On POSIX the PID may linger as a zombie until the parent reaps,
        # but Popen.wait() reaps it. After reap, os.kill should ESRCH.
        assert is_process_alive(proc.pid, recorded) is False
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
