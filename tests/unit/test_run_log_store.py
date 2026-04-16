"""Unit tests for RunLogStore — NDJSON log persistence with SHA256 integrity."""

from __future__ import annotations

import json
from uuid import uuid4

from app.services.run_log_store import RunLogStore


class TestRunLogStore:
    """Tests for NDJSON write, read, finalize, and integrity."""

    def test_open_creates_directory_and_file(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        agent_uuid = uuid4()
        run_uuid = uuid4()
        handle = store.open(agent_uuid, run_uuid)
        assert handle.path.exists()
        store.close(handle)

    def test_append_writes_ndjson_lines(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        handle = store.open(uuid4(), uuid4())
        store.append(handle, {"event_type": "llm_response", "stream": "assistant", "content": "hello"})
        store.append(handle, {"event_type": "tool_call", "stream": "tool", "content": "search"})
        store.close(handle)

        lines = handle.path.read_text().strip().split("\n")
        assert len(lines) == 2
        event1 = json.loads(lines[0])
        assert event1["seq"] == 1
        assert event1["event_type"] == "llm_response"
        event2 = json.loads(lines[1])
        assert event2["seq"] == 2

    def test_finalize_returns_sha256_and_byte_count(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        handle = store.open(uuid4(), uuid4())
        store.append(handle, {"event_type": "test", "stream": "system"})
        sha256, byte_count = store.finalize(handle)

        assert len(sha256) == 64  # hex digest
        assert byte_count > 0
        # Verify by re-hashing
        import hashlib

        actual_hash = hashlib.sha256(handle.path.read_bytes()).hexdigest()
        assert sha256 == actual_hash

    def test_finalize_is_idempotent_on_closed_file(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        handle = store.open(uuid4(), uuid4())
        store.append(handle, {"event_type": "test", "stream": "system"})
        sha1, bytes1 = store.finalize(handle)
        sha2, bytes2 = store.finalize(handle)
        assert sha1 == sha2
        assert bytes1 == bytes2

    def test_read_returns_events_after_seq(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        agent_uuid = uuid4()
        run_uuid = uuid4()
        handle = store.open(agent_uuid, run_uuid)
        for i in range(5):
            store.append(handle, {"event_type": f"event_{i}", "stream": "system"})
        store.finalize(handle)

        # Read all
        all_events = store.read(agent_uuid, run_uuid)
        assert len(all_events) == 5

        # Read after seq 3
        later_events = store.read(agent_uuid, run_uuid, after_seq=3)
        assert len(later_events) == 2
        assert later_events[0]["seq"] == 4

    def test_read_nonexistent_returns_empty(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        events = store.read(uuid4(), uuid4())
        assert events == []

    def test_append_includes_timestamp(self, tmp_path):
        store = RunLogStore(str(tmp_path))
        handle = store.open(uuid4(), uuid4())
        store.append(handle, {"event_type": "test", "stream": "system"})
        store.close(handle)

        line = handle.path.read_text().strip()
        event = json.loads(line)
        assert "ts" in event
        # ISO format check
        assert "T" in event["ts"]
