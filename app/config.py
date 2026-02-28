"""
Application settings loaded from environment variables and .env file.

All configuration lives here. Every other module imports from this module —
never from os.environ directly. Settings is instantiated once at module load
and injected via FastAPI's Depends() where needed.

Required variables (no defaults — startup fails if missing):
  - DATABASE_URL

All other variables have safe defaults suitable for local development.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"

    # ------------------------------------------------------------------
    # Task Queue
    # ------------------------------------------------------------------
    QUEUE_BACKEND: str = "postgres"  # "postgres" | "celery_redis" | "sqs" | "azure_service_bus"
    QUEUE_CONCURRENCY: int = 10
    QUEUE_MAX_RETRIES: int = 3
    QUEUE_RETRY_BACKOFF_SECONDS: int = 60

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    ENCRYPTION_KEY: str = ""

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
    # Secrets backends (optional — one or neither, never both)
    # ------------------------------------------------------------------
    AZURE_KEY_VAULT_URL: str = ""
    AWS_SECRETS_MANAGER_SECRET_NAME: str = ""
    AWS_REGION: str = ""

    # ------------------------------------------------------------------
    # Approval Notifications
    # ------------------------------------------------------------------
    APPROVAL_NOTIFIER: str = "none"  # "none" | "slack" | "teams"
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    TEAMS_WEBHOOK_URL: str = ""


settings = Settings()
