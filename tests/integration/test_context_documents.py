"""Integration tests for context document management — /v1/context-documents."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestContextDocumentCRUD:
    async def test_create_json_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "JSON Create Test",
                "document_type": "runbook",
                "is_global": False,
                "content": "# Runbook\nStep 1",
                "tags": ["test"],
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "JSON Create Test"
        assert data["document_type"] == "runbook"
        assert "uuid" in data

    async def test_create_with_targeting_rules(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Targeted Doc",
                "document_type": "playbook",
                "is_global": False,
                "content": "Targeted content",
                "tags": [],
                "targeting_rules": {
                    "match_any": [
                        {"field": "severity", "op": "in", "value": ["High", "Critical"]}
                    ]
                },
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["targeting_rules"] is not None

    async def test_create_multipart(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """Upload via multipart/form-data with a text file."""
        resp = await test_client.post(
            "/v1/context-documents",
            data={
                "title": "Multipart Test",
                "document_type": "sop",
                "is_global": "false",
                "tags": "tag1,tag2",
            },
            files={"file": ("test.txt", b"# SOP Content\nDo this.", "text/plain")},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_filter_by_type(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents?document_type=playbook",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_filter_by_global(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents?is_global=true",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for doc in resp.json()["data"]:
            assert doc["is_global"] is True

    async def test_get_by_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        uuid = sample_context_document["uuid"]
        resp = await test_client.get(
            f"/v1/context-documents/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == uuid
        assert "content" in data

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        uuid = sample_context_document["uuid"]
        resp = await test_client.patch(
            f"/v1/context-documents/{uuid}",
            json={"title": "Updated Title"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"

    async def test_patch_content(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        uuid = sample_context_document["uuid"]
        resp = await test_client.patch(
            f"/v1/context-documents/{uuid}",
            json={"content": "# Updated Content"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["content"] == "# Updated Content"

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_context_document: dict[str, Any],
    ) -> None:
        uuid = sample_context_document["uuid"]
        resp = await test_client.delete(
            f"/v1/context-documents/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestContextDocumentScope:
    async def test_alerts_read_can_list(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 200

    async def test_alerts_read_cannot_create(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Forbidden",
                "document_type": "runbook",
                "is_global": False,
                "content": "nope",
                "tags": [],
            },
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_enrichments_key_cannot_access(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents",
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 403
