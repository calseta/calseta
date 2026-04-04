"""Integration tests — Phase 6 KB sync providers.

Covers:
- GitHub sync: fetch + create page, hash-change detection, no-op on same hash
- Confluence sync: ADF-to-markdown path (via mock)
- URL sync: markitdown conversion path (via mock)
- Error handling: 404 → failure result, no crash
- Sync registry: provider lookup
- KBService hash-change detection
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_headers(scoped_api_key: Any) -> dict[str, str]:
    key: str = await scoped_api_key(["admin"])
    return auth_header(key)


async def _create_sync_page(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
    sync_source: dict,
) -> dict:
    resp = await client.post(
        "/v1/kb",
        json={
            "title": "Sync Test Page",
            "slug": slug,
            "body": "initial content",
            "folder": "/synced/",
            "status": "published",
            "sync_source": sync_source,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# GitHub sync provider unit tests
# ---------------------------------------------------------------------------


class TestGitHubSyncProvider:
    async def test_fetch_success_returns_updated_outcome(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Hello World\n\nContent from GitHub."

        provider = GitHubSyncProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch(
                sync_config={
                    "type": "github",
                    "repo": "org/repo",
                    "path": "docs/runbook.md",
                }
            )

        assert result.outcome == "updated"
        assert result.content is not None
        assert "Hello World" in result.content
        assert result.content_hash is not None

    async def test_fetch_404_returns_fetch_failed(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        mock_response = MagicMock()
        mock_response.status_code = 404

        provider = GitHubSyncProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch(
                sync_config={
                    "type": "github",
                    "repo": "org/repo",
                    "path": "docs/missing.md",
                }
            )

        assert result.outcome == "fetch_failed"
        assert result.error_message is not None

    async def test_fetch_missing_config_returns_config_invalid(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        provider = GitHubSyncProvider()
        result = await provider.fetch(sync_config={"type": "github"})
        assert result.outcome == "config_invalid"

    def test_validate_config_valid(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        provider = GitHubSyncProvider()
        errors = provider.validate_config(
            {"type": "github", "repo": "org/repo", "path": "docs/runbook.md"}
        )
        assert errors == []

    def test_validate_config_missing_path(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        provider = GitHubSyncProvider()
        errors = provider.validate_config({"type": "github", "repo": "org/repo"})
        assert len(errors) > 0

    def test_validate_config_missing_repo(self) -> None:
        from app.integrations.kb_sync.github_sync import GitHubSyncProvider

        provider = GitHubSyncProvider()
        errors = provider.validate_config({"type": "github", "path": "docs/a.md"})
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Confluence sync provider unit tests
# ---------------------------------------------------------------------------


class TestConfluenceSyncProvider:
    async def test_fetch_returns_updated_with_markdown(self) -> None:
        from app.integrations.kb_sync.confluence_sync import ConfluenceSyncProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "body": {"storage": {"value": "<p>Hello from Confluence</p>"}},
            "version": {"number": 5},
        }

        provider = ConfluenceSyncProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch(
                sync_config={
                    "type": "confluence",
                    "base_url": "https://example.atlassian.net",
                    "page_id": "123456",
                    "auth": {"type": "bearer", "token": "token123"},
                }
            )

        assert result.outcome == "updated"
        assert result.content is not None
        assert "Hello from Confluence" in result.content
        assert result.sync_source_ref == "5"

    def test_validate_config_requires_base_url_and_page_id(self) -> None:
        from app.integrations.kb_sync.confluence_sync import ConfluenceSyncProvider

        provider = ConfluenceSyncProvider()
        assert provider.validate_config(
            {"type": "confluence", "base_url": "https://x.atlassian.net", "page_id": "123"}
        ) == []
        assert len(provider.validate_config({"type": "confluence", "base_url": "https://x.atlassian.net"})) > 0


# ---------------------------------------------------------------------------
# URL sync provider unit tests
# ---------------------------------------------------------------------------


class TestURLSyncProvider:
    async def test_fetch_returns_updated_with_text(self) -> None:
        from app.integrations.kb_sync.url_sync import URLSyncProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Runbook\n\nStep 1: Do the thing."
        mock_response.headers = {"content-type": "text/plain"}

        provider = URLSyncProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch(
                sync_config={
                    "type": "url",
                    "url": "https://example.com/runbook.md",
                }
            )

        assert result.outcome == "updated"
        assert result.content is not None
        assert "Runbook" in result.content

    async def test_fetch_exception_returns_fetch_failed(self) -> None:
        from app.integrations.kb_sync.url_sync import URLSyncProvider

        provider = URLSyncProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_cls.return_value = mock_client

            result = await provider.fetch(
                sync_config={"type": "url", "url": "https://unreachable.example.com"}
            )

        assert result.outcome == "fetch_failed"
        assert result.error_message is not None

    def test_validate_config_requires_url(self) -> None:
        from app.integrations.kb_sync.url_sync import URLSyncProvider

        provider = URLSyncProvider()
        assert provider.validate_config({"url": "https://example.com"}) == []
        assert len(provider.validate_config({})) > 0


# ---------------------------------------------------------------------------
# Sync registry
# ---------------------------------------------------------------------------


class TestSyncRegistry:
    def test_get_github_provider(self) -> None:
        from app.integrations.kb_sync.registry import get_sync_provider

        provider = get_sync_provider("github")
        assert provider is not None

    def test_get_confluence_provider(self) -> None:
        from app.integrations.kb_sync.registry import get_sync_provider

        provider = get_sync_provider("confluence")
        assert provider is not None

    def test_get_url_provider(self) -> None:
        from app.integrations.kb_sync.registry import get_sync_provider

        provider = get_sync_provider("url")
        assert provider is not None

    def test_unknown_type_returns_none(self) -> None:
        from app.integrations.kb_sync.registry import get_sync_provider

        provider = get_sync_provider("unknown_provider_xyz")
        assert provider is None


# ---------------------------------------------------------------------------
# Hash-change detection via KBService
# ---------------------------------------------------------------------------


class TestKBSyncHashDetection:
    async def test_sync_page_hash_changed_updates_body(
        self,
        db_session: AsyncSession,
    ) -> None:
        """When fetched content differs from stored content, body is updated."""
        from app.db.models.kb_page import KnowledgeBasePage
        from app.integrations.kb_sync.base import SyncResult
        from app.repositories.kb_repository import KBPageRepository
        from app.services.kb_service import KBService

        # Create the page directly in the test session
        page = KnowledgeBasePage(
            title="Hash Change Test",
            slug="hash-changed-direct-page",
            body="initial content",
            folder="/synced/",
            status="published",
            inject_scope={},
            inject_pinned=False,
            latest_revision_number=1,
            sync_source={"type": "url", "url": "https://example.com/doc.md"},
            sync_last_hash="oldhash999",
        )
        db_session.add(page)
        await db_session.flush()
        await db_session.refresh(page)

        new_content = "Completely new content from remote source — version 2."
        mock_result = SyncResult(
            outcome="updated",
            content=new_content,
            content_hash="newhash123",
        )

        service = KBService(db_session)
        mock_provider = MagicMock()
        mock_provider.fetch = AsyncMock(return_value=mock_result)
        mock_provider.validate_config = MagicMock(return_value=[])  # no errors
        with patch("app.services.kb_service.get_sync_provider", return_value=mock_provider):
            await service.sync_page("hash-changed-direct-page")

        # Verify update in same session
        repo = KBPageRepository(db_session)
        updated = await repo.get_by_slug("hash-changed-direct-page")
        assert updated is not None
        assert updated.body == new_content
