"""Secrets management API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SecretCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    provider: str = Field(
        "local_encrypted",
        description="'local_encrypted' (AES-256-GCM in PostgreSQL) or 'env_var' (OS env var).",
    )
    env_var_name: str | None = Field(
        None,
        description=(
            "Required when provider is 'env_var'. "
            "Name of the OS environment variable that holds the value."
        ),
    )
    value: str | None = Field(
        None,
        description=(
            "Required when provider is 'local_encrypted'. "
            "Plaintext secret value; encrypted at rest."
        ),
    )

    @model_validator(mode="after")
    def _validate_provider_fields(self) -> SecretCreate:
        if self.provider == "local_encrypted":
            if not self.value:
                raise ValueError(
                    "'value' is required when provider is 'local_encrypted'."
                )
            if self.env_var_name is not None:
                raise ValueError(
                    "'env_var_name' must not be set when provider is 'local_encrypted'."
                )
        elif self.provider == "env_var":
            if not self.env_var_name:
                raise ValueError(
                    "'env_var_name' is required when provider is 'env_var'."
                )
            if self.value is not None:
                raise ValueError(
                    "'value' must not be set when provider is 'env_var'."
                )
        else:
            raise ValueError(
                f"Unknown provider '{self.provider}'. "
                "Valid values: 'local_encrypted', 'env_var'."
            )
        return self


class SecretRotate(BaseModel):
    value: str = Field(..., min_length=1, description="New plaintext value to encrypt and store.")


class SecretResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    description: str | None
    provider: str
    env_var_name: str | None
    current_version: int
    is_sensitive: bool
    created_at: datetime
    updated_at: datetime
    # value / encrypted_value are NEVER returned


class SecretVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    version: int
    is_current: bool
    created_at: datetime
    # encrypted_value is NEVER returned
