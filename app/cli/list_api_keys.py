"""
List all API keys (prefix, name, scopes, status).

Displays key metadata only — never exposes the key hash.

Usage:
    python -m app.cli.list_api_keys
    python -m app.cli.list_api_keys --active-only

Docker:
    docker compose exec api python -m app.cli.list_api_keys
"""

from __future__ import annotations

# TODO: Implement in a future chunk.
#
# Planned features:
#   - Table output of all keys: prefix, name, scopes, is_active, last_used_at, expires_at
#   - --active-only flag to filter inactive keys
#   - --json flag for machine-readable output
#   - Exit code 0 if keys exist, 1 if no keys found (useful in scripts)


def main() -> None:
    raise NotImplementedError(
        "list_api_keys is not yet implemented. "
        "Use the REST API: GET /v1/api-keys (requires admin scope)."
    )


if __name__ == "__main__":
    main()
