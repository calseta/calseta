"""GitHubSyncProvider — fetches a file from a GitHub repository via the REST API."""
from __future__ import annotations

import httpx

from app.integrations.kb_sync.base import SyncProviderBase, SyncResult, _resolve_token, _sha256


class GitHubSyncProvider(SyncProviderBase):
    """Fetch a single file from a GitHub repo.

    Required sync_config keys:
      repo   — "org/repo"
      path   — path within the repo, e.g. "docs/runbook.md"

    Optional sync_config keys:
      branch — defaults to "main"
      auth   — {"type": "secret_ref", "secret_name": "github_pat"}
                or {"type": "bearer", "token": "ghp_..."}
    """

    provider_type = "github"

    async def fetch(
        self,
        sync_config: dict,
        secret_resolver: object | None = None,
    ) -> SyncResult:
        repo = sync_config.get("repo", "")
        path = sync_config.get("path", "")
        branch = sync_config.get("branch", "main")

        if not repo or not path:
            return SyncResult(
                outcome="config_invalid",
                error_message="Missing required sync_config fields: repo, path",
            )

        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        params: dict[str, str] = {"ref": branch}
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "Calseta/1.0",
        }

        token = await _resolve_token(sync_config, secret_resolver)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params, headers=headers)

            if resp.status_code == 404:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message=f"File not found in GitHub repo: {path}",
                )
            if resp.status_code == 401:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message="GitHub authentication failed — check your PAT",
                )
            if resp.status_code != 200:
                return SyncResult(
                    outcome="fetch_failed",
                    error_message=f"GitHub API returned HTTP {resp.status_code}",
                )

            content = resp.text
            content_hash = _sha256(content)
            return SyncResult(outcome="updated", content=content, content_hash=content_hash)

        except Exception as exc:
            return SyncResult(outcome="fetch_failed", error_message=str(exc))

    def validate_config(self, sync_config: dict) -> list[str]:
        errors: list[str] = []
        if not sync_config.get("repo"):
            errors.append("Missing required field: repo")
        if not sync_config.get("path"):
            errors.append("Missing required field: path")
        return errors
