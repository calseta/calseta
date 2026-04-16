"""Unit tests for CALSETA_* environment variable builder (C5).

Tests ``build_agent_env`` and ``CalsetaEnvVar`` at ``app/runtime/env_builder.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.runtime.env_builder import CalsetaEnvVar, build_agent_env
from app.runtime.models import RuntimeContext


def _make_agent(
    uuid: UUID | None = None,
    name: str = "test-agent",
) -> MagicMock:
    """Build a mock AgentRegistration with required fields."""
    agent = MagicMock()
    agent.uuid = uuid or UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    agent.name = name
    return agent


def _make_context(
    agent_id: int = 1,
    task_key: str = "alert:99",
    heartbeat_run_id: int = 7,
    alert_id: int | None = None,
    run_uuid: UUID | None = None,
    wake_reason: str | None = None,
) -> RuntimeContext:
    """Build a RuntimeContext with controllable fields."""
    return RuntimeContext(
        agent_id=agent_id,
        task_key=task_key,
        heartbeat_run_id=heartbeat_run_id,
        alert_id=alert_id,
        run_uuid=run_uuid,
        wake_reason=wake_reason,
    )


# ---------------------------------------------------------------------------
# CalsetaEnvVar enum tests
# ---------------------------------------------------------------------------


class TestCalsetaEnvVar:
    """Validate enum naming invariants."""

    def test_all_values_start_with_calseta_prefix(self):
        """Every CalsetaEnvVar value must begin with 'CALSETA_'."""
        for member in CalsetaEnvVar:
            assert member.value.startswith("CALSETA_"), (
                f"{member.name} = {member.value!r} does not start with 'CALSETA_'"
            )

    def test_known_members_exist(self):
        """All documented env vars are present in the enum."""
        expected = {
            "AGENT_ID",
            "AGENT_NAME",
            "RUN_ID",
            "TASK_KEY",
            "WAKE_REASON",
            "API_URL",
            "API_KEY",
            "ALERT_UUID",
            "WORKSPACE_DIR",
        }
        actual = {m.name for m in CalsetaEnvVar}
        assert expected == actual


# ---------------------------------------------------------------------------
# build_agent_env tests
# ---------------------------------------------------------------------------


class TestBuildAgentEnv:
    """Tests for build_agent_env()."""

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_sets_agent_id(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent(uuid=UUID("11111111-2222-3333-4444-555555555555"))
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_AGENT_ID"] == "11111111-2222-3333-4444-555555555555"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_sets_agent_name(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent(name="triage-bot")
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_AGENT_NAME"] == "triage-bot"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_sets_task_key(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(task_key="issue:42")

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_TASK_KEY"] == "issue:42"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_sets_api_url_from_settings(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "https://api.calseta.io"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_API_URL"] == "https://api.calseta.io"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_includes_api_key_when_provided(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context()

        env = build_agent_env(agent, ctx, api_key="cai_scoped_test_key_1234")

        assert env["CALSETA_API_KEY"] == "cai_scoped_test_key_1234"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_excludes_api_key_when_none(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context()

        env = build_agent_env(agent, ctx, api_key=None)

        assert "CALSETA_API_KEY" not in env

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_includes_alert_uuid_when_set(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(alert_id=777)

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_ALERT_UUID"] == "777"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_excludes_alert_uuid_when_none(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(alert_id=None)

        env = build_agent_env(agent, ctx)

        assert "CALSETA_ALERT_UUID" not in env

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_includes_run_id_when_set(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        run_uuid = UUID("aaaa1111-bbbb-cccc-dddd-eeee22223333")
        ctx = _make_context(run_uuid=run_uuid)

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_RUN_ID"] == str(run_uuid)

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_excludes_run_id_when_none(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(run_uuid=None)

        env = build_agent_env(agent, ctx)

        assert "CALSETA_RUN_ID" not in env

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_inherits_existing_env_vars(self, mock_os, mock_settings):
        mock_os.environ = {"PATH": "/usr/bin", "HOME": "/home/test", "CUSTOM_VAR": "hello"}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/home/test"
        assert env["CUSTOM_VAR"] == "hello"
        # CALSETA vars are also present
        assert "CALSETA_AGENT_ID" in env

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_includes_wake_reason_when_set(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(wake_reason="comment")

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_WAKE_REASON"] == "comment"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_excludes_wake_reason_when_none(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        ctx = _make_context(wake_reason=None)

        env = build_agent_env(agent, ctx)

        assert "CALSETA_WAKE_REASON" not in env

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_sets_workspace_dir_from_settings(self, mock_os, mock_settings):
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/data/agent-files"

        agent = _make_agent(uuid=UUID("11111111-2222-3333-4444-555555555555"))
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_WORKSPACE_DIR"] == "/data/agent-files/11111111-2222-3333-4444-555555555555"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_calseta_vars_override_inherited_env(self, mock_os, mock_settings):
        """If os.environ has CALSETA_AGENT_ID, the builder overwrites it."""
        mock_os.environ = {"CALSETA_AGENT_ID": "stale-value"}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent(uuid=UUID("11111111-2222-3333-4444-555555555555"))
        ctx = _make_context()

        env = build_agent_env(agent, ctx)

        assert env["CALSETA_AGENT_ID"] == "11111111-2222-3333-4444-555555555555"

    @patch("app.runtime.env_builder.settings")
    @patch("app.runtime.env_builder.os")
    def test_full_env_dict_with_all_optional_fields(self, mock_os, mock_settings):
        """When all optional fields are provided, all CALSETA_* vars are present."""
        mock_os.environ = {}
        mock_settings.CALSETA_API_BASE_URL = "http://localhost:8000"
        mock_settings.AGENT_FILES_DIR = "/tmp/agents"

        agent = _make_agent()
        run_uuid = uuid4()
        ctx = _make_context(
            alert_id=100,
            run_uuid=run_uuid,
            wake_reason="retry",
        )

        env = build_agent_env(agent, ctx, api_key="cai_key123")

        expected_keys = {m.value for m in CalsetaEnvVar}
        for key in expected_keys:
            assert key in env, f"Expected {key} in env"
