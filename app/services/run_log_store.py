"""
NDJSON run log store — append-only file writer with SHA256 finalization.

Each agent run produces a log file at:
    {CALSETA_DATA_DIR}/logs/{agent_uuid}/{run_uuid}.ndjson

Usage:
    store = RunLogStore(data_dir)
    handle = store.open(agent_uuid, run_uuid)
    store.append(handle, event_dict)
    sha256, byte_count = store.finalize(handle)
    events = store.read(agent_uuid, run_uuid, after_seq=0)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RunLogHandle:
    """Open handle to an NDJSON log file."""

    agent_uuid: UUID
    run_uuid: UUID
    path: Path
    _file: Any = field(default=None, repr=False)
    _seq: int = field(default=0, repr=False)
    _byte_count: int = field(default=0, repr=False)


class RunLogStore:
    """NDJSON run log persistence with SHA256 integrity."""

    def __init__(self, data_dir: str) -> None:
        self._base = Path(data_dir) / "logs"

    def open(self, agent_uuid: UUID, run_uuid: UUID) -> RunLogHandle:
        """Create log directory and open a file handle for writing."""
        log_dir = self._base / str(agent_uuid)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{run_uuid}.ndjson"
        handle = RunLogHandle(
            agent_uuid=agent_uuid,
            run_uuid=run_uuid,
            path=path,
            _file=open(path, "a", encoding="utf-8"),  # noqa: SIM115
        )
        logger.debug(
            "run_log_opened",
            agent_uuid=str(agent_uuid),
            run_uuid=str(run_uuid),
            path=str(path),
        )
        return handle

    def append(self, handle: RunLogHandle, event: dict[str, Any]) -> None:
        """Write a single NDJSON event line."""
        handle._seq += 1
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "seq": handle._seq,
            **event,
        }
        line = (
            json.dumps(record, separators=(",", ":"), default=str)
            + "\n"
        )
        handle._file.write(line)
        handle._file.flush()
        handle._byte_count += len(line.encode("utf-8"))

    def finalize(self, handle: RunLogHandle) -> tuple[str, int]:
        """Close file and compute SHA256. Returns (sha256_hex, byte_count)."""
        if handle._file and not handle._file.closed:
            handle._file.close()

        sha256 = hashlib.sha256()
        total_bytes = 0
        with open(handle.path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
                total_bytes += len(chunk)

        digest = sha256.hexdigest()
        logger.info(
            "run_log_finalized",
            run_uuid=str(handle.run_uuid),
            sha256=digest,
            bytes=total_bytes,
        )
        return digest, total_bytes

    def read(
        self,
        agent_uuid: UUID,
        run_uuid: UUID,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        """Read events from NDJSON file, optionally after a sequence."""
        path = self._base / str(agent_uuid) / f"{run_uuid}.ndjson"
        if not path.exists():
            return []

        events: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if event.get("seq", 0) > after_seq:
                    events.append(event)
        return events

    def close(self, handle: RunLogHandle) -> None:
        """Close the file handle without finalizing."""
        if handle._file and not handle._file.closed:
            handle._file.close()
