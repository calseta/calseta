"""
DatabaseDrivenProvider — adapter that wraps a DB row (EnrichmentProvider model)
and implements EnrichmentProviderBase.

Credential resolution priority:
  1. Decrypted auth_config from DB (encrypted at rest)
  2. Env var fallback via env_var_mapping (for builtins)

This adapter delegates all HTTP execution to GenericHttpEnrichmentEngine.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType
from app.services.enrichment_engine import GenericHttpEnrichmentEngine

logger = structlog.get_logger(__name__)


def _decrypt_auth_config(auth_config: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt auth_config if it contains an _encrypted key."""
    if not auth_config:
        return {}

    encrypted = auth_config.get("_encrypted")
    if encrypted:
        from app.auth.encryption import decrypt_value

        try:
            decrypted_json = decrypt_value(encrypted)
            return json.loads(decrypted_json)
        except Exception:
            logger.warning("auth_config_decryption_failed")
            return {}

    return auth_config


def _resolve_env_vars(
    env_var_mapping: dict[str, str] | None,
) -> dict[str, Any]:
    """Resolve auth fields from environment variables."""
    if not env_var_mapping:
        return {}

    resolved: dict[str, Any] = {}
    for field_name, env_var in env_var_mapping.items():
        value = os.environ.get(env_var, "")
        if value:
            resolved[field_name] = value
    return resolved


class DatabaseDrivenProvider(EnrichmentProviderBase):
    """EnrichmentProviderBase implementation backed by a DB row."""

    def __init__(
        self,
        provider_name: str,
        display_name: str,
        supported_types: list[IndicatorType],
        http_config: dict[str, Any],
        auth_type: str,
        auth_config: dict[str, Any] | None,
        env_var_mapping: dict[str, str] | None,
        default_cache_ttl_seconds: int,
        cache_ttl_by_type: dict[str, int] | None,
        malice_rules: dict[str, Any] | None,
        field_extractions: list[dict[str, Any]],
        is_active: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self.display_name = display_name
        self.supported_types = supported_types
        self.cache_ttl_seconds = default_cache_ttl_seconds
        self._http_config = http_config
        self._auth_type = auth_type
        self._auth_config_raw = auth_config
        self._env_var_mapping = env_var_mapping
        self._cache_ttl_by_type = cache_ttl_by_type or {}
        self._malice_rules = malice_rules
        self._field_extractions = field_extractions
        self._is_active = is_active

        # Build _TTL_BY_TYPE for the base class get_cache_ttl()
        self._TTL_BY_TYPE = {
            IndicatorType(k): v for k, v in self._cache_ttl_by_type.items()
            if k in [t.value for t in IndicatorType]
        }

    def _resolve_auth(self) -> dict[str, Any]:
        """Resolve credentials: DB auth_config first, then env var fallback."""
        if self._auth_type == "no_auth":
            return {}

        # Try decrypted DB credentials first
        db_auth = _decrypt_auth_config(self._auth_config_raw)
        if db_auth:
            return db_auth

        # Fall back to env vars (for builtins using existing .env config)
        return _resolve_env_vars(self._env_var_mapping)

    def is_configured(self) -> bool:
        """Provider is configured if active and has credentials (or needs none)."""
        if not self._is_active:
            return False

        if self._auth_type == "no_auth":
            return True

        auth = self._resolve_auth()
        return bool(auth)

    async def enrich(
        self, value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Execute the HTTP enrichment pipeline. Never raises."""
        try:
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"{self.display_name} is not configured",
                )
            if indicator_type not in self.supported_types:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"{self.display_name} does not support '{indicator_type}'",
                )

            auth = self._resolve_auth()
            engine = GenericHttpEnrichmentEngine(
                provider_name=self.provider_name,
                http_config=self._http_config,
                malice_rules=self._malice_rules,
                field_extractions=self._field_extractions,
            )
            return await engine.execute(value, str(indicator_type), auth)

        except Exception as exc:
            logger.exception(
                "database_provider_enrich_error",
                provider=self.provider_name,
                indicator_type=str(indicator_type),
                value=value[:64],
            )
            return EnrichmentResult.failure_result(self.provider_name, str(exc))

    @classmethod
    def from_db_row(
        cls,
        row: Any,
        field_extractions: list[dict[str, Any]],
    ) -> DatabaseDrivenProvider:
        """Construct a DatabaseDrivenProvider from an ORM model instance.

        Args:
            row: EnrichmentProvider ORM model instance.
            field_extractions: List of extraction rule dicts for this provider.
        """
        supported = [
            IndicatorType(t) for t in (row.supported_indicator_types or [])
            if t in [it.value for it in IndicatorType]
        ]
        return cls(
            provider_name=row.provider_name,
            display_name=row.display_name,
            supported_types=supported,
            http_config=row.http_config or {},
            auth_type=row.auth_type or "no_auth",
            auth_config=row.auth_config,
            env_var_mapping=row.env_var_mapping,
            default_cache_ttl_seconds=row.default_cache_ttl_seconds or 3600,
            cache_ttl_by_type=row.cache_ttl_by_type,
            malice_rules=row.malice_rules,
            field_extractions=field_extractions,
            is_active=row.is_active,
        )
