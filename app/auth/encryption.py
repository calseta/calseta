"""
Fernet encryption utilities for at-rest secret storage.

Used for: agent auth_header_value, source_integration auth_config.
Key: settings.ENCRYPTION_KEY — must be a 32-byte url-safe base64 string.
     Generate with:
         python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If ENCRYPTION_KEY is not set (empty string), encryption raises ValueError.
This allows the platform to start without encryption configured but prevents
storing secrets without a key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import settings


def get_fernet() -> Fernet:
    """Return Fernet instance initialized from settings.ENCRYPTION_KEY."""
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY is not set. Cannot encrypt/decrypt secrets.")
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string; returns base64-encoded ciphertext."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string; returns plaintext."""
    return get_fernet().decrypt(ciphertext.encode()).decode()
