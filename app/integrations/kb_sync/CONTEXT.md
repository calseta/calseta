# KB Sync Integration — CONTEXT.md

## What this component does

The `kb_sync` integration is the external-source adapter layer for the knowledge base. It defines how KB pages whose `sync_source` JSONB field is populated get their content fetched and refreshed from external systems (GitHub repos, Confluence, arbitrary URLs). The `KBService.sync_page()` method calls into this layer; the periodic procrastinate task `sync_kb_pages_task` (every 6 hours) calls `KBService.sync_all_pages()`.

This layer never touches the database directly — it only fetches remote content and returns a typed `SyncResult`. The service layer handles persistence decisions.

---

## Interfaces

### `SyncResult` (dataclass)

| Field | Type | Meaning |
|---|---|---|
| `outcome` | `str` | `updated` / `no_change` / `fetch_failed` / `config_invalid` |
| `content` | `str \| None` | New page body (set on `updated` only) |
| `content_hash` | `str \| None` | SHA-256 hex digest of `content` |
| `error_message` | `str \| None` | Human-readable error (set on failure outcomes) |
| `sync_source_ref` | `str \| None` | Source-system version ref (commit SHA, Confluence version number) |

### `SyncProviderBase` ABC

```python
class SyncProviderBase(ABC):
    provider_type: str  # registered key in _REGISTRY

    async def fetch(self, sync_config: dict, secret_resolver=None) -> SyncResult:
        """Must never raise. Catch all exceptions; return fetch_failed on error."""

    def validate_config(self, sync_config: dict) -> list[str]:
        """Return validation errors. Empty list = valid."""
```

### Registry

```python
from app.integrations.kb_sync.registry import get_sync_provider
provider = get_sync_provider("github")  # returns GitHubSyncProvider instance or None
```

---

## Sync config shape by provider

### `github` / `github_wiki`
```json
{
  "type": "github",
  "repo": "org/repo",
  "path": "docs/runbook.md",
  "branch": "main",
  "auth": {"type": "secret_ref", "secret_name": "github_pat"}
}
```

### `confluence`
```json
{
  "type": "confluence",
  "base_url": "https://myorg.atlassian.net",
  "page_id": "12345678",
  "auth": {"type": "bearer", "token": "atatt3x..."}
}
```

### `url`
```json
{
  "type": "url",
  "url": "https://example.com/runbook.md"
}
```

---

## Key design decisions

1. **Providers never raise.** All errors are returned as `SyncResult(outcome="fetch_failed")`. This makes `sync_all_pages()` robust — a single failing source cannot abort the batch.

2. **Hash-based change detection.** Providers return `content_hash` (SHA-256). The service compares this to `page.sync_last_hash` to skip unnecessary DB writes and revision creation. This means syncing an unchanged Confluence page costs zero DB writes after the first sync.

3. **No polling in this layer.** This layer is purely on-demand. Scheduling (6-hour cron) lives in `app/queue/registry.py` as `sync_kb_pages_task`. The service decides what to sync; the provider decides how to fetch.

4. **`github_wiki` reuses `GitHubSyncProvider`.** GitHub Wikis are accessible via the same Contents API with a `_wiki/` path prefix. Using the same provider class avoids duplication.

5. **Confluence storage XML → markdown is best-effort.** The conversion handles the most common constructs (headings, bold, italic, code blocks, lists). It does not aim for perfect fidelity — the goal is agent-readable text, not lossless round-trip.

6. **`markitdown` is optional for URL sync.** If `markitdown` is unavailable or conversion fails, `URLSyncProvider` falls back to raw text. This keeps the provider usable even without the optional dependency.

---

## Extension pattern: adding a new sync provider

1. Create `app/integrations/kb_sync/{name}_sync.py` with a class extending `SyncProviderBase`.
2. Set `provider_type = "your_type"` on the class.
3. Implement `fetch()` — wrap all I/O in try/except, return `SyncResult` for all paths.
4. Optionally override `validate_config()` to check required fields.
5. Register an instance in `app/integrations/kb_sync/registry.py`:
   ```python
   from app.integrations.kb_sync.your_sync import YourSyncProvider
   _REGISTRY["your_type"] = YourSyncProvider()
   ```
6. No other code changes needed — the service calls `get_sync_provider(sync_type)` which reads from this registry.

---

## Common failure modes

| Failure | Outcome | Diagnosis |
|---|---|---|
| Wrong sync_config keys | `config_invalid` | `validate_config()` returns errors; check page `sync_source` JSONB |
| Unknown `type` in sync_source | `config_invalid` | `get_sync_provider()` returns None; add to registry if needed |
| HTTP 401 from GitHub | `fetch_failed` | PAT expired or missing; check `auth.secret_name` resolves correctly |
| HTTP 404 from GitHub | `fetch_failed` | Wrong `repo`, `path`, or `branch` in sync_config |
| Confluence 401 | `fetch_failed` | API token expired; check `auth` in sync_config |
| URL unreachable | `fetch_failed` | Network error; `error_message` contains the exception string |
| `markitdown` not installed | fallback to raw text | Not a failure — URLSyncProvider falls back gracefully |

---

## Test coverage

Tests live in `tests/integrations/test_kb_sync.py` (Phase 6):
- `TestGitHubSyncProvider` — mocked httpx, covers 200/404/401/network error
- `TestConfluenceSyncProvider` — mocked httpx, covers storage XML conversion
- `TestURLSyncProvider` — mocked httpx, covers plain text, HTML (markitdown fallback)
- `TestSyncRegistry` — all types resolvable, unknown type returns None
