"""Unit tests for the hardened secret resolver (S3).

Covers ``resolve_secret_ref`` in :mod:`app.integrations.llm.factory` and the
denylist module in :mod:`app.secrets.denylist`.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.auth.encryption import encrypt_value
from app.integrations.llm.factory import (
    InvalidSecretRef,
    has_known_prefix,
    resolve_secret_ref,
)
from app.secrets.denylist import is_denied

# ---------------------------------------------------------------------------
# Denylist
# ---------------------------------------------------------------------------


class TestDenylist:
    @pytest.mark.parametrize(
        "name",
        [
            "CALSETA_API_KEY",
            "CALSETA_AGENT_ID",
            "CALSETA_RUN_ID",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "OKTA_API_TOKEN",
            "GITHUB_TOKEN",
            "DB_PASSWORD",
            "MY_SECRET",
            "DATABASE_URL",
            "ENCRYPTION_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AZURE_CLIENT_SECRET",
        ],
    )
    def test_denied_names(self, name: str):
        assert is_denied(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "PATH",
            "HOME",
            "LANG",
            "USER_PREFERENCE",
            "FEATURE_FLAG_X",
            "MY_VAR",
        ],
    )
    def test_allowed_names(self, name: str):
        assert is_denied(name) is False

    def test_empty_name_is_not_denied(self):
        # Defensive — empty string never matches a pattern. The resolver
        # raises InvalidSecretRef("empty") before ever reaching is_denied.
        assert is_denied("") is False


# ---------------------------------------------------------------------------
# resolve_secret_ref — error branches
# ---------------------------------------------------------------------------


class TestResolverErrors:
    def test_literal_value_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("literal-value")
        assert exc.value.reason == "unknown_prefix"

    def test_empty_string_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("")
        assert exc.value.reason == "empty"

    def test_whitespace_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("   ")
        assert exc.value.reason == "empty"

    def test_none_returns_empty_string(self):
        # None means "no key configured" (e.g. claude_code subscription).
        # The resolver returns "" rather than raising so the factory can
        # still construct the adapter.
        assert resolve_secret_ref(None) == ""

    def test_env_prefix_with_no_name_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("env:")
        assert exc.value.reason == "empty"

    def test_enc_prefix_with_no_ciphertext_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("enc:")
        assert exc.value.reason == "empty"


# ---------------------------------------------------------------------------
# resolve_secret_ref — env: prefix
# ---------------------------------------------------------------------------


class TestEnvResolver:
    def test_reads_from_environment(self):
        with patch.dict(os.environ, {"MY_TEST_VAR": "hello-world"}, clear=False):
            assert resolve_secret_ref("env:MY_TEST_VAR") == "hello-world"

    def test_missing_env_returns_empty_string(self):
        # Missing env var is not fatal — caller decides.
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_secret_ref("env:NEVER_SET_VAR") == ""

    def test_denylisted_env_var_database_url_raises(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://..."}, clear=False):
            with pytest.raises(InvalidSecretRef) as exc:
                resolve_secret_ref("env:DATABASE_URL")
            assert exc.value.reason == "denied"

    def test_denylisted_env_var_encryption_key_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("env:ENCRYPTION_KEY")
        assert exc.value.reason == "denied"

    def test_denylisted_env_var_calseta_prefix_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("env:CALSETA_API_KEY")
        assert exc.value.reason == "denied"

    def test_denylisted_env_var_aws_prefix_raises(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("env:AWS_REGION")
        assert exc.value.reason == "denied"


# ---------------------------------------------------------------------------
# resolve_secret_ref — enc: prefix (Fernet round-trip)
# ---------------------------------------------------------------------------


class TestEncResolver:
    def test_round_trip_decrypts(self, monkeypatch):
        # Use a real Fernet key for the round-trip test.
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            "app.config.settings.ENCRYPTION_KEY", key, raising=False
        )
        plaintext = "sk-ant-real-secret-value"
        ciphertext = encrypt_value(plaintext)

        result = resolve_secret_ref(f"enc:{ciphertext}")

        assert result == plaintext

    def test_invalid_ciphertext_raises(self, monkeypatch):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            "app.config.settings.ENCRYPTION_KEY", key, raising=False
        )
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("enc:not-valid-fernet-data")
        assert exc.value.reason == "decrypt_failed"


# ---------------------------------------------------------------------------
# resolve_secret_ref — backend prefixes (vault/aws-sm/azure-kv)
# ---------------------------------------------------------------------------


class TestBackendResolvers:
    def test_vault_unconfigured_raises_backend_unavailable(self):
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("vault:llm/anthropic")
        assert exc.value.reason == "backend_unavailable"

    def test_aws_sm_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.AWS_SECRETS_MANAGER_SECRET_NAME",
            "",
            raising=False,
        )
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("aws-sm:my-secret")
        assert exc.value.reason == "backend_unavailable"

    def test_azure_kv_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.AZURE_KEY_VAULT_URL", "", raising=False
        )
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("azure-kv:my-secret")
        assert exc.value.reason == "backend_unavailable"

    def test_aws_sm_configured_but_backend_not_wired_raises(self, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.AWS_SECRETS_MANAGER_SECRET_NAME",
            "calseta-prod",
            raising=False,
        )
        # Backend isn't wired into the resolver yet — must still fail closed.
        with pytest.raises(InvalidSecretRef) as exc:
            resolve_secret_ref("aws-sm:my-secret")
        assert exc.value.reason == "backend_unavailable"


# ---------------------------------------------------------------------------
# has_known_prefix helper (used by startup auto-migration)
# ---------------------------------------------------------------------------


class TestHasKnownPrefix:
    @pytest.mark.parametrize(
        "ref",
        [
            "env:MY_KEY",
            "enc:gAAAAA...",
            "vault:llm/anthropic",
            "aws-sm:my-secret",
            "azure-kv:my-secret",
        ],
    )
    def test_known_prefixes(self, ref: str):
        assert has_known_prefix(ref) is True

    @pytest.mark.parametrize(
        "ref",
        [
            "literal-value",
            "sk-ant-abcdef",
            "",
            None,
            "ENV:UPPERCASE",  # case sensitive
            "vault",  # no colon
        ],
    )
    def test_unknown_prefixes(self, ref):
        assert has_known_prefix(ref) is False
