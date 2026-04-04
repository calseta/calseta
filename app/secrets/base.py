"""Abstract base class for all secrets providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SecretsProviderBase(ABC):
    """Port interface for resolving and storing secret values.

    Implementations:
      - LocalEncryptedProvider: AES-256 (Fernet) encryption stored in PostgreSQL.
      - EnvVarProvider: reads from OS environment variables; read-only.
    """

    @abstractmethod
    async def resolve(self, name: str) -> str | None:
        """Resolve a secret by name. Returns None if not found or not configured."""
        ...

    @abstractmethod
    async def store(self, name: str, value: str) -> None:
        """Persist a new secret value.

        Raises NotImplementedError for read-only providers (e.g. EnvVarProvider).
        """
        ...
