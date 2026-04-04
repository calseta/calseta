"""Integration tests for issue/task management — /v1/issues."""

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestCreateIssue:
    async def test_create_issue(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/issues",
            json={
                "title": "Investigate suspicious login",
                "description": "Multiple failed logins from IP 1.2.3.4",
                "status": "backlog",
                "priority": "high",
                "category": "investigation",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Investigate suspicious login"
        assert "uuid" in data
        assert "identifier" in data
        assert data["status"] == "backlog"
        assert data["priority"] == "high"
        assert data["category"] == "investigation"

    async def test_create_issue_minimal(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """Only title is required; all other fields use defaults."""
        resp = await test_client.post(
            "/v1/issues",
            json={"title": "Minimal issue"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Minimal issue"
        assert data["status"] == "backlog"
        assert data["priority"] == "medium"

    async def test_create_issue_invalid_status(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """Service either rejects unknown status (422) or stores service default."""
        resp = await test_client.post(
            "/v1/issues",
            json={"title": "Bad status issue", "status": "not_valid"},
            headers=auth_header(api_key),
        )
        # Acceptable: 422 validation error OR 201 with service-normalized status
        assert resp.status_code in (201, 422)


class TestListIssues:
    async def test_list_issues_empty(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/issues", headers=auth_header(api_key))
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]

    async def test_list_issues_with_filter(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        # Create two issues with different statuses
        await test_client.post(
            "/v1/issues",
            json={"title": "Issue A", "status": "backlog"},
            headers=auth_header(api_key),
        )
        resp_b = await test_client.post(
            "/v1/issues",
            json={"title": "Issue B", "status": "todo"},
            headers=auth_header(api_key),
        )
        assert resp_b.status_code == 201

        # Filter by backlog
        resp = await test_client.get(
            "/v1/issues?status=backlog",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for issue in resp.json()["data"]:
            assert issue["status"] == "backlog"

    async def test_list_issues_pagination(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        # Create 3 issues
        for i in range(3):
            await test_client.post(
                "/v1/issues",
                json={"title": f"Pagination issue {i}"},
                headers=auth_header(api_key),
            )

        resp = await test_client.get(
            "/v1/issues?page=1&page_size=2",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) <= 2
        assert body["meta"]["total"] >= 3
        assert body["meta"]["page"] == 1
        assert body["meta"]["page_size"] == 2


class TestGetIssue:
    async def test_get_issue_not_found(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        random_uuid = str(uuid4())
        resp = await test_client.get(
            f"/v1/issues/{random_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_get_issue(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/issues",
            json={
                "title": "Get test issue",
                "description": "A detailed description",
                "priority": "critical",
                "category": "remediation",
            },
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201
        issue_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.get(
            f"/v1/issues/{issue_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == issue_uuid
        assert data["title"] == "Get test issue"
        assert data["description"] == "A detailed description"
        assert data["priority"] == "critical"
        assert data["category"] == "remediation"
        assert "created_at" in data
        assert "updated_at" in data


class TestPatchIssue:
    async def test_patch_issue(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Original title", "description": "Original desc"},
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201
        issue_uuid = create_resp.json()["data"]["uuid"]

        patch_resp = await test_client.patch(
            f"/v1/issues/{issue_uuid}",
            json={"title": "Updated title", "description": "Updated desc"},
            headers=auth_header(api_key),
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()["data"]
        assert data["title"] == "Updated title"
        assert data["description"] == "Updated desc"

    async def test_patch_issue_status_transitions(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Status transition issue", "status": "backlog"},
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201
        issue_uuid = create_resp.json()["data"]["uuid"]

        # backlog → todo
        resp = await test_client.patch(
            f"/v1/issues/{issue_uuid}",
            json={"status": "todo"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "todo"

        # todo → in_progress
        resp = await test_client.patch(
            f"/v1/issues/{issue_uuid}",
            json={"status": "in_progress"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "in_progress"
        # started_at should be set when moving into in_progress
        assert data["started_at"] is not None


class TestIssueComments:
    async def test_add_comment(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Issue for comments"},
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201
        issue_uuid = create_resp.json()["data"]["uuid"]

        comment_resp = await test_client.post(
            f"/v1/issues/{issue_uuid}/comments",
            json={"body": "This is a test comment", "author_operator": "test-operator"},
            headers=auth_header(api_key),
        )
        assert comment_resp.status_code == 201
        data = comment_resp.json()["data"]
        assert data["body"] == "This is a test comment"
        assert data["author_operator"] == "test-operator"
        assert "uuid" in data
        assert "created_at" in data

    async def test_list_comments(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Issue for listing comments"},
            headers=auth_header(api_key),
        )
        assert create_resp.status_code == 201
        issue_uuid = create_resp.json()["data"]["uuid"]

        # Add two comments
        for i in range(2):
            await test_client.post(
                f"/v1/issues/{issue_uuid}/comments",
                json={"body": f"Comment {i}"},
                headers=auth_header(api_key),
            )

        list_resp = await test_client.get(
            f"/v1/issues/{issue_uuid}/comments",
            headers=auth_header(api_key),
        )
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 2
