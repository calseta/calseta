"""Unit tests for ``SecretsAccessor`` allowlist + denylist enforcement (S3).

Defined in :mod:`app.workflows.context`. The S1 IPC ``secret.get`` op
proxies these same semantics into the sandboxed subprocess; whatever
behavior the in-process accessor has here is the contract S1 mimics.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from app.workflows.context import SecretsAccessor


class TestSecretsAccessorDenylist:
    """Denylist always wins, regardless of allowlist content."""

    def test_denylisted_name_returns_none_even_when_allowed(self):
        accessor = SecretsAccessor(allowed_secrets=["DATABASE_URL"])
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgres://x"}, clear=False
        ):
            assert accessor.get("DATABASE_URL") is None

    def test_denylisted_calseta_name_returns_none(self):
        accessor = SecretsAccessor(allowed_secrets=["CALSETA_API_KEY"])
        with patch.dict(
            os.environ, {"CALSETA_API_KEY": "cak_abc"}, clear=False
        ):
            assert accessor.get("CALSETA_API_KEY") is None

    def test_anthropic_api_key_denied(self):
        accessor = SecretsAccessor(allowed_secrets=["ANTHROPIC_API_KEY"])
        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "sk-ant-x"}, clear=False
        ):
            # Even on the allowlist, denylist (suffix _API_KEY) wins.
            assert accessor.get("ANTHROPIC_API_KEY") is None


class TestSecretsAccessorAllowlist:
    """Names not on allowlist return None even when env var is set."""

    def test_not_on_allowlist_returns_none(self):
        accessor = SecretsAccessor(allowed_secrets=[])
        with patch.dict(
            os.environ, {"OKTA_DOMAIN": "example.okta.com"}, clear=False
        ):
            assert accessor.get("OKTA_DOMAIN") is None

    def test_default_allowlist_is_empty(self):
        # No constructor arg → workflow has zero secrets available.
        accessor = SecretsAccessor()
        with patch.dict(
            os.environ, {"OKTA_DOMAIN": "example.okta.com"}, clear=False
        ):
            assert accessor.get("OKTA_DOMAIN") is None

    def test_on_allowlist_and_env_set_returns_value(self):
        accessor = SecretsAccessor(allowed_secrets=["OKTA_DOMAIN"])
        with patch.dict(
            os.environ, {"OKTA_DOMAIN": "example.okta.com"}, clear=False
        ):
            assert accessor.get("OKTA_DOMAIN") == "example.okta.com"

    def test_on_allowlist_but_env_missing_returns_none(self):
        accessor = SecretsAccessor(allowed_secrets=["NEVER_SET_VAR"])
        with patch.dict(os.environ, {}, clear=True):
            assert accessor.get("NEVER_SET_VAR") is None

    def test_none_allowlist_treated_as_empty(self):
        accessor = SecretsAccessor(allowed_secrets=None)
        with patch.dict(os.environ, {"FOO": "bar"}, clear=False):
            assert accessor.get("FOO") is None


class TestSecretsAccessorOrdering:
    """Denylist is checked before allowlist."""

    def test_denylist_check_runs_first(self):
        # If the order were reversed (allowlist first), this would return
        # the value because DATABASE_URL is on the allowlist. Denylist
        # wins.
        accessor = SecretsAccessor(allowed_secrets=["DATABASE_URL", "FOO"])
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgres://x", "FOO": "bar"},
            clear=False,
        ):
            assert accessor.get("DATABASE_URL") is None
            assert accessor.get("FOO") == "bar"
