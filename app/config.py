"""
Application settings loaded from environment variables and optional cloud secrets backends.

Priority order (highest to lowest):
    1. Azure Key Vault      (if AZURE_KEY_VAULT_URL is set)
    2. AWS Secrets Manager  (if AWS_SECRETS_MANAGER_SECRET_NAME is set)
    3. Environment variables
    4. .env file
    5. Defaults

Only one cloud backend is active at a time. If neither is configured, neither SDK
is imported — no startup overhead for self-hosters.

Required variables (no defaults — startup fails with a clear error if missing):
    - DATABASE_URL

All other variables have safe defaults suitable for local development.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# Use stdlib logger here (not structlog) — structlog isn't configured yet
# when config.py is imported at process startup.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional secrets source: Azure Key Vault
# ---------------------------------------------------------------------------

class _AzureKeyVaultSource(PydanticBaseSettingsSource):
    """
    Loads secrets from Azure Key Vault at startup.
    Only imported/instantiated when AZURE_KEY_VAULT_URL is non-empty.
    """

    def __init__(self, settings_cls: type[BaseSettings], vault_url: str) -> None:
        super().__init__(settings_cls)
        self._vault_url = vault_url

    def get_field_value(self, field: Any, field_name: str) -> Any:  # type: ignore[override]
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore[import]
            from azure.keyvault.secrets import SecretClient  # type: ignore[import]

            client = SecretClient(
                vault_url=self._vault_url,
                credential=DefaultAzureCredential(),
            )
            values: dict[str, Any] = {}
            for secret in client.list_properties_of_secrets():
                if secret.name:
                    try:
                        sv = client.get_secret(secret.name)
                        # Azure KV secret names use hyphens; map back to underscores
                        key = secret.name.replace("-", "_").upper()
                        values[key] = sv.value
                    except Exception:
                        pass
            logger.info("secrets_source=azure_key_vault loaded=%d", len(values))
            return values
        except Exception as exc:
            logger.error("Azure Key Vault load failed: %s", exc)
            return {}

    def field_is_complex(self, field: Any) -> bool:  # type: ignore[override]
        return False


# ---------------------------------------------------------------------------
# Optional secrets source: AWS Secrets Manager
# ---------------------------------------------------------------------------

class _AWSSecretsManagerSource(PydanticBaseSettingsSource):
    """
    Loads secrets from AWS Secrets Manager at startup.
    Secret value must be a JSON object whose keys match Settings field names.
    Only imported/instantiated when AWS_SECRETS_MANAGER_SECRET_NAME is non-empty.
    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        secret_name: str,
        region: str,
    ) -> None:
        super().__init__(settings_cls)
        self._secret_name = secret_name
        self._region = region

    def get_field_value(self, field: Any, field_name: str) -> Any:  # type: ignore[override]
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        try:
            import boto3  # type: ignore[import]

            client = boto3.client("secretsmanager", region_name=self._region)
            response = client.get_secret_value(SecretId=self._secret_name)
            raw = response.get("SecretString", "{}")
            values: dict[str, Any] = json.loads(raw)
            logger.info("secrets_source=aws_secrets_manager loaded=%d", len(values))
            return values
        except Exception as exc:
            logger.error("AWS Secrets Manager load failed: %s", exc)
            return {}

    def field_is_complex(self, field: Any) -> bool:  # type: ignore[override]
        return False


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Required — no defaults; startup fails with a clear error if missing
    # ------------------------------------------------------------------
    DATABASE_URL: str

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_VERSION: str = "dev"

    # ------------------------------------------------------------------
    # Alert Deduplication
    # ------------------------------------------------------------------
    ALERT_DEDUP_WINDOW_HOURS: int = 24  # 0 = disabled

    # ------------------------------------------------------------------
    # MCP Server
    # ------------------------------------------------------------------
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8001

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"

    # ------------------------------------------------------------------
    # Task Queue
    # ------------------------------------------------------------------
    QUEUE_BACKEND: str = "postgres"
    QUEUE_CONCURRENCY: int = 10
    QUEUE_MAX_RETRIES: int = 3
    QUEUE_RETRY_BACKOFF_SECONDS: int = 60

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    ENCRYPTION_KEY: str = ""

    # ------------------------------------------------------------------
    # SSRF Protection
    # ------------------------------------------------------------------
    # Comma-separated hostnames exempt from SSRF checks.
    # Use for dev (e.g. "host.docker.internal,localhost") — never in prod.
    SSRF_ALLOWED_HOSTS: str = ""

    # ------------------------------------------------------------------
    # Rate Limiting
    # ------------------------------------------------------------------
    RATE_LIMIT_UNAUTHED_PER_MINUTE: int = 30
    RATE_LIMIT_AUTHED_PER_MINUTE: int = 600
    RATE_LIMIT_INGEST_PER_MINUTE: int = 100
    RATE_LIMIT_ENRICHMENT_PER_MINUTE: int = 60
    RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE: int = 30
    TRUSTED_PROXY_COUNT: int = 0

    # ------------------------------------------------------------------
    # Security Headers
    # ------------------------------------------------------------------
    HTTPS_ENABLED: bool = False
    SECURITY_HEADER_HSTS_ENABLED: bool = True

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ALLOWED_ORIGINS: str = ""
    CORS_ALLOW_ALL_ORIGINS: bool = False

    # ------------------------------------------------------------------
    # Request Body Limits
    # ------------------------------------------------------------------
    MAX_REQUEST_BODY_SIZE_MB: int = 10
    MAX_INGEST_PAYLOAD_SIZE_MB: int = 5

    # ------------------------------------------------------------------
    # Webhook Signing Secrets
    # ------------------------------------------------------------------
    SENTINEL_WEBHOOK_SECRET: str = ""
    ELASTIC_WEBHOOK_SECRET: str = ""
    SPLUNK_WEBHOOK_SECRET: str = ""

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    CACHE_BACKEND: str = "memory"  # "memory" only in v1; "redis" in future

    # ------------------------------------------------------------------
    # Enrichment Providers
    # ------------------------------------------------------------------
    VIRUSTOTAL_API_KEY: str = ""
    ABUSEIPDB_API_KEY: str = ""
    OKTA_DOMAIN: str = ""
    OKTA_API_TOKEN: str = ""
    ENTRA_TENANT_ID: str = ""
    ENTRA_CLIENT_ID: str = ""
    ENTRA_CLIENT_SECRET: str = ""

    # ------------------------------------------------------------------
    # Cloud Secrets Backends (optional — at most one active)
    # ------------------------------------------------------------------
    AZURE_KEY_VAULT_URL: str = ""
    AWS_SECRETS_MANAGER_SECRET_NAME: str = ""
    AWS_REGION: str = ""

    # ------------------------------------------------------------------
    # AI / LLM (Chunk 4.7 — workflow generation)
    # ------------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""

    # ------------------------------------------------------------------
    # Base URLs
    # ------------------------------------------------------------------
    # Public URL (Teams card links, approval callbacks)
    CALSETA_BASE_URL: str = "http://localhost:8000"
    CALSETA_API_BASE_URL: str = "http://localhost:8000"  # Included in agent webhook payloads

    # ------------------------------------------------------------------
    # Approval Notifications
    # ------------------------------------------------------------------
    APPROVAL_NOTIFIER: str = "none"  # "none" | "slack" | "teams"
    APPROVAL_DEFAULT_TIMEOUT_SECONDS: int = 3600
    APPROVAL_DEFAULT_CHANNEL: str = ""  # Slack channel ID (e.g. "C0123456789") — use ID, not name
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    TEAMS_WEBHOOK_URL: str = ""

    # ------------------------------------------------------------------
    # Sandbox
    # ------------------------------------------------------------------
    ENRICHMENT_MOCK_MODE: bool = False
    SANDBOX_MODE: bool = False
    SANDBOX_RESET_INTERVAL_HOURS: int = 24

    @model_validator(mode="after")
    def _validate_encryption_key(self) -> Settings:
        """Warn if ENCRYPTION_KEY is missing or not a valid Fernet key.

        Does NOT raise — the app starts regardless. Encryption operations
        fail at runtime via ``get_fernet()`` if the key is invalid.
        This keeps dev/test environments working while surfacing a clear
        warning that operators can act on before enabling encryption.
        """
        _gen_hint = (
            "Generate with: python -c "
            '"from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
        if self.ENCRYPTION_KEY:
            import base64

            key_bytes = self.ENCRYPTION_KEY.encode()
            valid = False
            if len(key_bytes) == 44:
                try:
                    decoded = base64.urlsafe_b64decode(key_bytes)
                    valid = len(decoded) == 32
                except Exception:
                    pass
            if not valid:
                logger.warning(
                    "ENCRYPTION_KEY is set but is not a valid "
                    "44-character Fernet key. Encryption operations "
                    "will fail at runtime. %s",
                    _gen_hint,
                )
        else:
            logger.warning(
                "ENCRYPTION_KEY is not set. Encryption features "
                "will fail at runtime if used. %s",
                _gen_hint,
            )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Build the source priority chain. Cloud backends are inserted at the
        top only when their trigger env vars are present.

        Priority (highest first):
            Azure Key Vault  → AWS Secrets Manager → env vars → .env → defaults
        """
        # Read trigger vars directly from the environment (before Settings loads)
        import os

        azure_url = os.getenv("AZURE_KEY_VAULT_URL", "")
        aws_secret = os.getenv("AWS_SECRETS_MANAGER_SECRET_NAME", "")
        aws_region = os.getenv("AWS_REGION", "")

        sources: list[PydanticBaseSettingsSource] = [init_settings]

        if azure_url:
            sources.append(_AzureKeyVaultSource(settings_cls, azure_url))
            _log_secrets_source("azure_key_vault")
        elif aws_secret:
            sources.append(_AWSSecretsManagerSource(settings_cls, aws_secret, aws_region))
            _log_secrets_source("aws_secrets_manager")
        else:
            _log_secrets_source("environment")

        sources.extend([env_settings, dotenv_settings, file_secret_settings])
        return tuple(sources)


def _log_secrets_source(source: str) -> None:
    """Emit the startup log line indicating which secrets source is active."""
    logger.info("secrets_source=%s", source)


settings = Settings()
