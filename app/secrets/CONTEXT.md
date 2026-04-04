# Secrets Management

## What This Component Does

The secrets system stores and resolves sensitive values (LLM API keys, integration credentials, agent tokens) securely. It provides a provider-based abstraction with two concrete backends: `local_encrypted` (AES-256 via Fernet, encrypted value stored in `secret_versions` table) and `env_var` (reads from environment variable at resolution time, nothing stored). Resolution happens via a string-ref format (`env:<VAR>`, `secret:<name>`, or literal). All resolved values are kept out of logs via caller convention — the resolver never logs the resolved value.

## Interfaces

### SecretsProviderBase (`base.py`)

```python
class SecretsProviderBase(ABC):
    async def resolve(self, name: str) -> str | None:
        """Resolve by name. Returns None if not found or var missing."""
    
    async def store(self, name: str, value: str) -> None:
        """Persist a new value. EnvVarProvider raises NotImplementedError."""
```

### resolve_secret_ref (`resolver.py`)

The primary entry point for all callers:

```python
async def resolve_secret_ref(ref: str, db: AsyncSession) -> str | None:
```

Ref format dispatch:
| Ref format | Resolution |
|---|---|
| `env:VARNAME` | `os.environ.get("VARNAME")` — no DB access |
| `secret:mykey` | DB lookup → `secrets.provider` → correct provider |
| anything else | Returned as-is (literal value for dev/testing) |

### SecretService (`app/services/secret_service.py`)

Used by route handlers only:

```python
async def create(data: SecretCreate) -> tuple[Secret, None]   # plaintext never returned
async def rotate(secret: Secret, new_value: str) -> SecretVersion
async def delete(secret: Secret) -> None
async def resolve(name: str) -> str | None
```

### REST API

```
POST   /v1/secrets                      Create (admin scope)
GET    /v1/secrets                      List (agents:read scope)
GET    /v1/secrets/{uuid}               Get metadata — value never returned
DELETE /v1/secrets/{uuid}               Delete + all versions (admin scope)
POST   /v1/secrets/{uuid}/versions      Rotate — store new encrypted version (admin scope)
GET    /v1/secrets/{uuid}/versions      List version metadata (admin scope)
```

## Key Design Decisions

**Why two providers instead of a unified interface?**
`env_var` secrets exist for operators who manage secrets externally (dotenv, Kubernetes secrets, AWS Parameter Store at the container level). They want Calseta to _reference_ those vars, not re-encrypt them. The `env_var` provider makes that path explicit without special-casing in the resolver.

**Why Fernet for local_encrypted?**
Calseta already uses `cryptography` (Fernet) for `auth_header_value_encrypted` on agent registrations (`app/auth/encryption.py`). Reusing the same key (`ENCRYPTION_KEY`) and library keeps the crypto surface minimal and avoids introducing a second key management concern.

**Why version history?**
Secret rotation is a compliance requirement for many orgs. Keeping old versions (with `is_current=False`) allows auditors to verify rotation happened and provides a rollback path. Hard-delete of versions happens only when the parent secret is deleted.

**Literal passthrough for dev convenience**
When `api_key_ref` contains a literal key (no `env:` or `secret:` prefix), `resolve_secret_ref` returns it unchanged. This lets local dev set `api_key_ref = "sk-ant-xxx"` without a full secrets setup. **Never do this in production** — the key is stored plaintext in the DB.

## Extension Pattern

To add a new secrets provider (e.g., HashiCorp Vault):

1. Create `app/secrets/vault_provider.py`:
```python
class VaultProvider(SecretsProviderBase):
    def __init__(self, db: AsyncSession) -> None: ...
    async def resolve(self, name: str) -> str | None:
        # vault_addr from VAULT_ADDR env var
        # authenticate via VAULT_TOKEN or AppRole
        # read from kv/data/{name}
        ...
    async def store(self, name: str, value: str) -> None:
        raise NotImplementedError("Vault provider is read-only from Calseta")
```

2. Add `"vault"` to the `provider` field's allowed values in `app/schemas/secrets.py`.

3. Update `app/secrets/resolver.py` to dispatch `secret.provider == "vault"` to `VaultProvider`.

4. Add `"vault"` to the provider enum in `SecretCreate` schema validator.

No migration needed — the `provider` column is `TEXT`, not a PostgreSQL ENUM.

## Common Failure Modes

**`resolve_secret_ref` returns `None` unexpectedly**
- `env:VARNAME` — the env var is not set in the worker/API process (check Docker Compose `environment:` section)
- `secret:name` — the secret name doesn't match (names are case-sensitive); check via `GET /v1/secrets`
- `local_encrypted` secret with no current version — secret was created but `store()` was never called; `current_version` will be 0

**Decryption fails with `InvalidToken`**
`ENCRYPTION_KEY` changed after the secret was stored. Fernet keys are not rotatable without re-encrypting all versions. If the key changes, all existing `local_encrypted` secrets become unreadable. Keep the key stable; rotate it via the `rotate_encryption_key` CLI command which re-encrypts all values.

**`store()` fails with `IntegrityError`**
The `(secret_id, version)` unique constraint was violated — a concurrent rotation race. The `SecretService.rotate()` method does not use advisory locks; if two requests rotate the same secret simultaneously, one will fail. This is acceptable — the retry pattern is: call `GET /v1/secrets/{uuid}/versions`, find the actual current version, and retry.

**`EnvVarProvider.store()` raises `NotImplementedError`**
Callers attempting to `store()` on an env_var secret need to use `rotate()` which calls the provider — but `env_var` secrets cannot be stored from Calseta. The operator must update the environment variable and restart the process. The API returns 400 for rotation attempts on env_var secrets.

## Test Coverage

```
tests/integration/agent_control_plane/test_phase1_llm_providers.py
  - Secret ref resolution (env: prefix, secret: prefix, literal)
  - Create + resolve via local_encrypted provider
  - Rotation creates new version, old version retained
  - Deletion cascades to all versions
```

Unit tests for `LocalEncryptedProvider` and `EnvVarProvider` should mock the DB session and assert encrypt/decrypt round-trips. The resolver integration test uses a real PostgreSQL test instance (same pattern as all Calseta integration tests — see `tests/conftest.py`).
