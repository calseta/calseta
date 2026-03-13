# Authentication and API Key Management

## What This Component Does

The auth component authenticates every API request using `cai_`-prefixed API keys validated against bcrypt hashes stored in the `api_keys` table. It provides a layered abstraction (`AuthBackendBase` -> `APIKeyAuthBackend`) designed for future backend swaps (e.g. BetterAuth), scope-based authorization via FastAPI dependency injection, structured audit logging for all authentication failures, and Fernet encryption utilities for at-rest secret storage.

## Interfaces

### AuthBackendBase (`base.py`)

Abstract authentication interface. Routes import only this -- never a concrete backend:

```python
class AuthBackendBase(ABC):
    async def authenticate(self, request: Request) -> AuthContext: ...
    # Raises CalsetaException(code="UNAUTHORIZED", status_code=401) on failure
```

### AuthContext (`base.py`)

Populated on every successful authentication:

```python
@dataclass
class AuthContext:
    key_prefix: str              # First 8 chars of the API key (for display, rate limiting, audit)
    scopes: list[str]            # e.g. ["alerts:read", "alerts:write"]
    key_id: int                  # Internal DB row ID (for last_used_at updates)
    allowed_sources: list[str] | None = None  # Source restriction (None = unrestricted)
```

### APIKeyAuthBackend (`api_key_backend.py`)

Concrete v1 implementation. Auth flow:

```
1. Extract "Authorization: Bearer cai_xxx" header
2. Slice key_prefix = first 8 chars
3. Look up APIKey row by prefix
4. Verify bcrypt hash via bcrypt.checkpw()
5. Check expiry (raises KEY_EXPIRED if past expires_at)
6. Update last_used_at in the session (committed with the request)
7. Return AuthContext
```

Every failure path calls `log_auth_failure()` before raising `CalsetaException`.

### Scopes (`scopes.py`)

```python
class Scope(StrEnum):
    ALERTS_READ = "alerts:read"
    ALERTS_WRITE = "alerts:write"
    ENRICHMENTS_READ = "enrichments:read"
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_WRITE = "workflows:write"
    WORKFLOWS_EXECUTE = "workflows:execute"
    APPROVALS_WRITE = "approvals:write"
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"
    ADMIN = "admin"             # Superscope -- passes every check
```

### Dependencies (`dependencies.py`)

Two FastAPI dependencies for route handlers:

```python
# Authentication only (any valid key):
async def get_auth_context(request, db) -> AuthContext

# Authentication + scope enforcement:
def require_scope(*scopes: Scope) -> Callable[..., Awaitable[AuthContext]]
```

Usage in routes:

```python
# Require authentication:
@router.get("/items")
async def list_items(auth: AuthContext = Depends(get_auth_context)):
    ...

# Require specific scope:
@router.post("/items")
async def create_item(auth: AuthContext = Depends(require_scope(Scope.ALERTS_WRITE))):
    ...

# Require one of several scopes (OR):
@router.get("/items")
async def read_items(auth: AuthContext = Depends(require_scope(Scope.ALERTS_READ, Scope.ADMIN))):
    ...
```

`admin` is a superscope: a key with `admin` passes every scope check without needing individual scopes.

### Audit Logging (`audit.py`)

```python
def log_auth_failure(reason: str, request: Request, key_prefix=None, required_scope=None) -> None
```

Single function for all auth failure logging. Emits structured JSON via structlog:

```json
{"event": "auth_failure", "reason": "invalid_key", "method": "POST", "path": "/v1/alerts", "key_prefix": "cai_abcd"}
```

Reason codes: `missing_header`, `invalid_format`, `invalid_key`, `key_expired`, `insufficient_scope`, `invalid_signature`.

### Encryption (`encryption.py`)

Fernet encryption for at-rest secret storage (agent auth headers, source integration auth configs):

```python
def encrypt_value(plaintext: str) -> str   # returns base64 ciphertext
def decrypt_value(ciphertext: str) -> str  # returns plaintext
def get_fernet() -> Fernet                 # raises ValueError if ENCRYPTION_KEY not set
```

Key: `settings.ENCRYPTION_KEY` -- a 32-byte url-safe base64 string. Generate with:
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If `ENCRYPTION_KEY` is not set, the platform starts normally but `encrypt_value()` / `decrypt_value()` raise `ValueError`. This allows running without encryption for development but prevents storing secrets without a key.

## Key Design Decisions

1. **Abstract backend for BetterAuth readiness.** `AuthBackendBase` is the port; `APIKeyAuthBackend` is the adapter. When BetterAuth (session-based auth with SSO/OAuth) ships in v2, a new `BetterAuthBackend` will implement the same interface. Route code uses `Depends(get_auth_context)` and never imports a concrete backend, so the swap is a one-line change in `dependencies.py`.

2. **bcrypt for key hashing, not SHA-256.** bcrypt's work factor makes brute-force attacks computationally expensive even if the hash table is leaked. SHA-256 would be fast to verify but also fast to brute-force. The full API key is shown once at creation and never stored.

3. **Key prefix for lookup, not the full key.** The first 8 characters of the key (`cai_xxxx`) are stored in `key_prefix` as a non-sensitive index. This allows O(1) lookup by prefix before the expensive bcrypt verification. The prefix is safe to log and display.

4. **`last_used_at` updated in the request session, not a separate write.** `APIKeyAuthBackend.authenticate()` sets `record.last_used_at = datetime.now(UTC)` and flushes, but the actual commit happens when the request session is committed. This avoids a separate DB roundtrip for usage tracking.

5. **All auth failures logged through one function.** `log_auth_failure()` is the single place that emits auth failure events. This ensures consistent log format, makes it easy to set up alerts on auth failures, and is straightforward to test.

6. **Scope enforcement is OR-logic, not AND.** `require_scope(Scope.ALERTS_READ, Scope.ADMIN)` passes if the key has EITHER scope. This matches the common pattern where `admin` should access everything. For AND-logic, chain multiple `Depends()` calls.

## Extension Pattern: Adding a New Scope

1. **Add to `app/auth/scopes.py`**:
   ```python
   class Scope(StrEnum):
       ...
       MY_ENTITY_READ = "my_entity:read"
       MY_ENTITY_WRITE = "my_entity:write"
   ```

2. **Use in route handlers**:
   ```python
   @router.get("/my-entity")
   async def list_entities(auth: AuthContext = Depends(require_scope(Scope.MY_ENTITY_READ))):
       ...
   ```

3. **Include in API key creation**: When creating keys via `POST /v1/api-keys`, include the new scope in the `scopes` array.

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| 401 "Missing or invalid Authorization header" | No `Authorization` header or not using `Bearer` prefix | Check request headers; must be `Authorization: Bearer cai_xxx` |
| 401 "Invalid API key format" | Key doesn't start with `cai_` or is too short | Key must be at least 8 characters and start with `cai_` |
| 401 "Invalid API key" | Key prefix not found in DB, or bcrypt hash mismatch | Check `api_keys` table for a row with matching `key_prefix` |
| 401 "API key has expired" | `expires_at` is in the past | Update or recreate the key with a future expiry |
| 403 "Insufficient scope" | Key lacks the required scope for this endpoint | Check key's `scopes` array; `admin` bypasses all checks |
| `ValueError: ENCRYPTION_KEY is not set` | Attempting to encrypt/decrypt without `ENCRYPTION_KEY` env var | Set `ENCRYPTION_KEY` to a valid Fernet key; generate with the command above |
| `auth_failure` log spam | Automated scanning or misconfigured client | Check `key_prefix` and `path` in logs to identify the source |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/test_auth.py` | Unit tests: valid key authentication, invalid key rejection, expired key rejection, bcrypt verification, scope enforcement (admin superscope, OR-logic, missing scope), `log_auth_failure()` structured output |
| `tests/integration/test_auth.py` | Full HTTP request auth flow: valid Bearer header, missing header, invalid format, wrong key, expired key |
| `tests/integration/test_api_keys.py` | API key CRUD: creation (returns full key once), list (shows prefix only), deletion, scope assignment |
| `tests/integration/test_response_contracts.py` | Verifies 401/403 error response format matches `{"error": {"code": "...", "message": "..."}}` |
