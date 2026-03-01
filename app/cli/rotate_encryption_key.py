"""
Rotate the ENCRYPTION_KEY used for encrypting sensitive fields at rest.

Re-encrypts all encrypted fields (agent auth headers, source auth configs)
from the old key to the new key in a single transaction.

Usage:
    python -m app.cli.rotate_encryption_key --old-key <old> --new-key <new>
    python -m app.cli.rotate_encryption_key --old-key <old> --new-key <new> --dry-run

Docker:
    docker compose exec api python -m app.cli.rotate_encryption_key \
      --old-key "old-key-here" --new-key "new-key-here"
"""

from __future__ import annotations

# TODO: Implement in a future chunk.
#
# Planned features:
#   - Accept --old-key and --new-key arguments
#   - --dry-run flag: decrypt all fields with old key, encrypt with new key,
#     but rollback instead of committing (verifies the rotation would succeed)
#   - Tables to re-encrypt:
#       * agent_registrations.auth_header_value (Fernet encrypted)
#       * source_integrations.auth_config (Fernet encrypted JSONB)
#   - Transaction safety: all-or-nothing commit
#   - Reports count of re-encrypted records per table
#   - Verifies new key can decrypt all re-encrypted values before committing
#   - After running: update ENCRYPTION_KEY in .env / secrets manager, restart services


def main() -> None:
    raise NotImplementedError(
        "rotate_encryption_key is not yet implemented. "
        "To rotate manually: update ENCRYPTION_KEY in .env, re-encrypt affected records "
        "in agent_registrations and source_integrations tables."
    )


if __name__ == "__main__":
    main()
