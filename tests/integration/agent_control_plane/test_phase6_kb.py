"""Integration tests — Phase 6 Knowledge Base (KB) CRUD and search.

Covers:
- Create / get / patch / delete KB pages
- Slug uniqueness enforcement
- Full-text search
- Revision history (auto-created on body change)
- Folder listing
- inject_scope field round-trips
- Auth enforcement (admin required for mutations)
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_key(scoped_api_key: Any, scopes: list[str] | None = None) -> str:
    if scopes is None:
        scopes = ["admin"]
    result: str = await scoped_api_key(scopes)
    return result


async def _create_page(
    client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Test KB Page",
        "slug": "test-kb-page",
        "body": "This is a test knowledge base page about security incidents.",
        "folder": "/runbooks/",
        "status": "published",
        **overrides,
    }
    resp = await client.post("/v1/kb", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    result: dict[str, object] = resp.json()["data"]
    return result


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestKBPageCreate:
    async def test_create_returns_201(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        resp = await test_client.post(
            "/v1/kb",
            json={
                "title": "My First Page",
                "slug": "my-first-page",
                "body": "Hello world.",
                "folder": "/docs/",
                "status": "draft",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["slug"] == "my-first-page"
        assert data["title"] == "My First Page"
        assert data["status"] == "draft"

    async def test_create_sets_revision_1(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(test_client, headers, slug="rev-test-page-1")
        assert page["latest_revision_number"] == 1

    async def test_duplicate_slug_409(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        await _create_page(test_client, headers, slug="dup-slug-page")
        resp = await test_client.post(
            "/v1/kb",
            json={"title": "Dup", "slug": "dup-slug-page", "body": "x", "folder": "/"},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_create_requires_admin(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await scoped_api_key(["alerts:read"])
        resp = await test_client.post(
            "/v1/kb",
            json={"title": "x", "slug": "x-slug", "body": "x", "folder": "/"},
            headers=auth_header(key),
        )
        assert resp.status_code == 403


class TestKBPageGet:
    async def test_get_by_slug(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        admin_key = await _admin_key(scoped_api_key)
        headers = auth_header(admin_key)
        await _create_page(test_client, headers, slug="get-test-slug")

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb/get-test-slug",
            headers=auth_header(read_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["slug"] == "get-test-slug"

    async def test_get_missing_404(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb/does-not-exist-xyz",
            headers=auth_header(key),
        )
        assert resp.status_code == 404

    async def test_list_pages(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        admin_key = await _admin_key(scoped_api_key)
        headers = auth_header(admin_key)
        await _create_page(test_client, headers, slug="list-page-a", folder="/list-folder/")
        await _create_page(test_client, headers, slug="list-page-b", folder="/list-folder/")

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb",
            params={"folder": "/list-folder/"},
            headers=auth_header(read_key),
        )
        assert resp.status_code == 200
        data = resp.json()
        slugs = [p["slug"] for p in data["data"]]
        assert "list-page-a" in slugs
        assert "list-page-b" in slugs


class TestKBPagePatch:
    async def test_patch_body_bumps_revision(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(test_client, headers, slug="patch-rev-page")
        assert page["latest_revision_number"] == 1

        resp = await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"body": "Updated body content for revision bump test."},
            headers=headers,
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["latest_revision_number"] == 2

    async def test_patch_title_no_revision_bump(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(test_client, headers, slug="patch-title-page")

        resp = await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"title": "New Title Only"},
            headers=headers,
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]
        # No body change → revision stays at 1
        assert updated["latest_revision_number"] == 1

    async def test_patch_requires_admin(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        admin_key = await _admin_key(scoped_api_key)
        headers = auth_header(admin_key)
        page = await _create_page(test_client, headers, slug="patch-auth-page")

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"title": "Hack"},
            headers=auth_header(read_key),
        )
        assert resp.status_code == 403


class TestKBPageDelete:
    async def test_delete_removes_page(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(test_client, headers, slug="delete-test-page")

        resp = await test_client.delete(
            f"/v1/kb/{page['slug']}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Confirm gone
        resp2 = await test_client.get(
            f"/v1/kb/{page['slug']}",
            headers=headers,
        )
        assert resp2.status_code == 404

    async def test_delete_requires_admin(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        admin_key = await _admin_key(scoped_api_key)
        headers = auth_header(admin_key)
        page = await _create_page(test_client, headers, slug="delete-auth-page")

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.delete(
            f"/v1/kb/{page['slug']}",
            headers=auth_header(read_key),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


class TestKBSearch:
    async def test_search_returns_matching_pages(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)

        # Create pages with distinctive content
        await _create_page(
            test_client, headers,
            slug="search-phishing-page",
            title="Phishing Investigation Runbook",
            body="How to investigate phishing emails and malicious domains.",
            status="published",
        )
        await _create_page(
            test_client, headers,
            slug="search-unrelated-page",
            title="Unrelated Documentation",
            body="This page is about something completely different.",
            status="published",
        )

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb/search",
            params={"q": "phishing"},
            headers=auth_header(read_key),
        )
        assert resp.status_code == 200
        results = resp.json()["data"]
        slugs = [r["slug"] for r in results]
        assert "search-phishing-page" in slugs

    async def test_search_requires_query(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb/search",
            headers=auth_header(key),
        )
        assert resp.status_code == 422  # missing required q param


# ---------------------------------------------------------------------------
# Revision history
# ---------------------------------------------------------------------------


class TestKBRevisions:
    async def test_get_revisions_list(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(test_client, headers, slug="revisions-list-page")

        # Make 2 more body edits
        await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"body": "Revision 2 body."},
            headers=headers,
        )
        await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"body": "Revision 3 body."},
            headers=headers,
        )

        resp = await test_client.get(
            f"/v1/kb/{page['slug']}/revisions",
            headers=headers,
        )
        assert resp.status_code == 200
        revisions = resp.json()["data"]
        assert len(revisions) == 3
        nums = {r["revision_number"] for r in revisions}
        assert nums == {1, 2, 3}

    async def test_get_specific_revision(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)
        page = await _create_page(
            test_client, headers, slug="revision-fetch-page",
            body="Original content.",
        )
        await test_client.patch(
            f"/v1/kb/{page['slug']}",
            json={"body": "Updated content."},
            headers=headers,
        )

        resp = await test_client.get(
            f"/v1/kb/{page['slug']}/revisions/1",
            headers=headers,
        )
        assert resp.status_code == 200
        rev = resp.json()["data"]
        assert rev["revision_number"] == 1
        assert rev["body"] == "Original content."


# ---------------------------------------------------------------------------
# Folder listing
# ---------------------------------------------------------------------------


class TestKBFolders:
    async def test_folders_returns_tree(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)

        await _create_page(test_client, headers, slug="folder-a-page", folder="/runbooks/")
        await _create_page(test_client, headers, slug="folder-b-page", folder="/playbooks/")

        read_key = await scoped_api_key(["alerts:read"])
        resp = await test_client.get(
            "/v1/kb/folders",
            headers=auth_header(read_key),
        )
        assert resp.status_code == 200
        folders = resp.json()["data"]
        names = [f["name"] for f in folders]
        assert "runbooks" in names or "/runbooks/" in names or any("runbook" in n for n in names)


# ---------------------------------------------------------------------------
# inject_scope round-trip
# ---------------------------------------------------------------------------


class TestKBInjectScope:
    async def test_inject_scope_global_stored(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)

        page = await _create_page(
            test_client, headers,
            slug="scope-global-page",
            inject_scope={"global": True},
        )
        assert page.get("inject_scope") == {"global": True}

    async def test_inject_scope_role_stored(
        self,
        test_client: AsyncClient,
        scoped_api_key: Any,
    ) -> None:
        key = await _admin_key(scoped_api_key)
        headers = auth_header(key)

        page = await _create_page(
            test_client, headers,
            slug="scope-role-page",
            inject_scope={"roles": ["triage", "analyst"]},
        )
        assert page.get("inject_scope") == {"roles": ["triage", "analyst"]}
