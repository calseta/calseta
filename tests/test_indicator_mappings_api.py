"""
API integration tests for indicator field mappings CRUD — /v1/indicator-mappings.

Tests cover:
  - POST /v1/indicator-mappings — create custom mapping (201)
  - GET /v1/indicator-mappings — list with filters
  - GET /v1/indicator-mappings/{uuid} — get by UUID
  - PATCH /v1/indicator-mappings/{uuid} — update a mapping
  - DELETE /v1/indicator-mappings/{uuid} — delete a mapping
  - System mapping deletion protection (422)
  - System mapping field_path modification protection (422)
  - System mapping is_active toggle (allowed)
  - Scope enforcement (admin required)
  - Seeder idempotency via API (system mappings count stable across restarts)

These tests use the real FastAPI test client with rolled-back DB transactions
via the conftest fixtures (db_session, test_client, api_key).
"""

from __future__ import annotations

import secrets
from typing import Any

import bcrypt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey


def auth_header(key: str) -> dict[str, str]:
    """Return a dict suitable for passing as ``headers=`` to httpx."""
    return {"Authorization": f"Bearer {key}"}


@pytest_asyncio.fixture
async def alerts_read_key(db_session: AsyncSession) -> str:
    """Create an API key with only alerts:read scope (insufficient for mappings)."""
    plain_key = "cai_" + secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()
    record = APIKey(
        name="test-alerts-read-key",
        key_prefix=plain_key[:8],
        key_hash=key_hash,
        scopes=["alerts:read"],
        is_active=True,
    )
    db_session.add(record)
    await db_session.flush()
    return plain_key


# ---------------------------------------------------------------------------
# Helper: create a custom mapping via the API
# ---------------------------------------------------------------------------


async def _create_custom_mapping(
    test_client: AsyncClient,
    api_key: str,
    *,
    source_name: str = "generic",
    field_path: str = "custom.ip_field",
    indicator_type: str = "ip",
    extraction_target: str = "raw_payload",
    is_active: bool = True,
    description: str = "Test mapping",
) -> dict[str, Any]:
    resp = await test_client.post(
        "/v1/indicator-mappings",
        json={
            "source_name": source_name,
            "field_path": field_path,
            "indicator_type": indicator_type,
            "extraction_target": extraction_target,
            "is_active": is_active,
            "description": description,
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /v1/indicator-mappings — Create custom mapping
# ---------------------------------------------------------------------------


class TestCreateIndicatorMapping:
    async def test_create_custom_mapping_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        data = await _create_custom_mapping(test_client, api_key)
        assert data["field_path"] == "custom.ip_field"
        assert data["indicator_type"] == "ip"
        assert data["extraction_target"] == "raw_payload"
        assert data["is_system"] is False
        assert data["is_active"] is True
        assert data["source_name"] == "generic"
        assert data["uuid"] is not None

    async def test_create_normalized_target_mapping(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        data = await _create_custom_mapping(
            test_client,
            api_key,
            field_path="custom_normalized_field",
            extraction_target="normalized",
        )
        assert data["extraction_target"] == "normalized"

    async def test_create_global_mapping_no_source_name(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        data = await _create_custom_mapping(
            test_client, api_key, source_name=None  # type: ignore[arg-type]
        )
        assert data["source_name"] is None

    async def test_create_all_indicator_types(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """Verify all 8 indicator types can be used in custom mappings."""
        types = ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"]
        for idx, itype in enumerate(types):
            data = await _create_custom_mapping(
                test_client,
                api_key,
                field_path=f"test.field_{idx}",
                indicator_type=itype,
            )
            assert data["indicator_type"] == itype

    async def test_create_mapping_is_not_system(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """Custom mappings created via API should always have is_system=False."""
        data = await _create_custom_mapping(test_client, api_key)
        assert data["is_system"] is False

    async def test_create_with_description(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        data = await _create_custom_mapping(
            test_client,
            api_key,
            description="Custom mapping for Okta IP extraction",
        )
        assert data["description"] == "Custom mapping for Okta IP extraction"


# ---------------------------------------------------------------------------
# GET /v1/indicator-mappings — List with filters
# ---------------------------------------------------------------------------


class TestListIndicatorMappings:
    async def test_list_returns_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert "meta" in resp.json()

    async def test_list_includes_custom_mapping(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.get(
            "/v1/indicator-mappings",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        uuids = [m["uuid"] for m in resp.json()["data"]]
        assert created["uuid"] in uuids

    async def test_filter_by_source_name(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        await _create_custom_mapping(
            test_client, api_key, source_name="sentinel", field_path="sentinel.custom_ip"
        )
        resp = await test_client.get(
            "/v1/indicator-mappings?source_name=sentinel",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["source_name"] == "sentinel"

    async def test_filter_by_is_system_true(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["is_system"] is True

    async def test_filter_by_is_system_false(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        await _create_custom_mapping(test_client, api_key)
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=false",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["is_system"] is False

    async def test_filter_by_extraction_target(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        await _create_custom_mapping(
            test_client, api_key, extraction_target="raw_payload"
        )
        resp = await test_client.get(
            "/v1/indicator-mappings?extraction_target=raw_payload",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["extraction_target"] == "raw_payload"

    async def test_filter_by_is_active(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        await _create_custom_mapping(
            test_client, api_key, is_active=False, field_path="inactive.field"
        )
        resp = await test_client.get(
            "/v1/indicator-mappings?is_active=false",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["is_active"] is False

    async def test_pagination(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings?page=1&page_size=5",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 5
        assert len(resp.json()["data"]) <= 5


# ---------------------------------------------------------------------------
# GET /v1/indicator-mappings/{uuid} — Get by UUID
# ---------------------------------------------------------------------------


class TestGetIndicatorMapping:
    async def test_get_by_uuid_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.get(
            f"/v1/indicator-mappings/{created['uuid']}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["uuid"] == created["uuid"]
        assert resp.json()["data"]["field_path"] == created["field_path"]

    async def test_get_nonexistent_uuid_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_get_invalid_uuid_422(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings/not-a-valid-uuid",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /v1/indicator-mappings/{uuid} — Update a mapping
# ---------------------------------------------------------------------------


class TestPatchIndicatorMapping:
    async def test_patch_is_active(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{created['uuid']}",
            json={"is_active": False},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    async def test_patch_field_path(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{created['uuid']}",
            json={"field_path": "updated.path"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["field_path"] == "updated.path"

    async def test_patch_description(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{created['uuid']}",
            json={"description": "Updated description"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["description"] == "Updated description"

    async def test_patch_indicator_type(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(
            test_client, api_key, indicator_type="ip"
        )
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{created['uuid']}",
            json={"indicator_type": "domain"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["indicator_type"] == "domain"

    async def test_patch_nonexistent_uuid_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.patch(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            json={"is_active": False},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/indicator-mappings/{uuid} — Delete a mapping
# ---------------------------------------------------------------------------


class TestDeleteIndicatorMapping:
    async def test_delete_custom_mapping_204(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        created = await _create_custom_mapping(test_client, api_key)
        resp = await test_client.delete(
            f"/v1/indicator-mappings/{created['uuid']}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = await test_client.get(
            f"/v1/indicator-mappings/{created['uuid']}",
            headers=auth_header(api_key),
        )
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_uuid_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.delete(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# System mapping protection
# ---------------------------------------------------------------------------


class TestSystemMappingProtection:
    async def _get_system_mapping_uuid(
        self, test_client: AsyncClient, api_key: str
    ) -> str | None:
        """Find the UUID of any system mapping, or None if none exist."""
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=1",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        if not data:
            return None
        return data[0]["uuid"]

    async def test_system_mapping_cannot_be_deleted(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """System mappings should return 422 on DELETE."""
        uuid = await self._get_system_mapping_uuid(test_client, api_key)
        if uuid is None:
            pytest.skip("No system mappings found — seeder may not have run")

        resp = await test_client.delete(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SYSTEM_MAPPING_READONLY"

    async def test_system_mapping_field_path_readonly(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """System mappings should reject field_path changes."""
        uuid = await self._get_system_mapping_uuid(test_client, api_key)
        if uuid is None:
            pytest.skip("No system mappings found — seeder may not have run")

        resp = await test_client.patch(
            f"/v1/indicator-mappings/{uuid}",
            json={"field_path": "hacked.field"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SYSTEM_MAPPING_READONLY"

    async def test_system_mapping_is_active_can_be_toggled(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """System mappings allow toggling is_active (the only permitted change)."""
        uuid = await self._get_system_mapping_uuid(test_client, api_key)
        if uuid is None:
            pytest.skip("No system mappings found — seeder may not have run")

        # Deactivate
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{uuid}",
            json={"is_active": False},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

        # Re-activate
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{uuid}",
            json={"is_active": True},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is True

    async def test_system_mapping_still_exists_after_delete_attempt(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """System mapping should still be retrievable after a failed delete attempt."""
        uuid = await self._get_system_mapping_uuid(test_client, api_key)
        if uuid is None:
            pytest.skip("No system mappings found — seeder may not have run")

        # Attempt to delete (should fail with 422)
        await test_client.delete(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )

        # Verify still exists
        resp = await test_client.get(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_system"] is True


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------


class TestIndicatorMappingScopes:
    async def test_list_requires_admin(
        self, test_client: AsyncClient, alerts_read_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_create_requires_admin(
        self, test_client: AsyncClient, alerts_read_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/indicator-mappings",
            json={
                "source_name": "generic",
                "field_path": "test.field",
                "indicator_type": "ip",
                "extraction_target": "raw_payload",
            },
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_patch_requires_admin(
        self, test_client: AsyncClient, alerts_read_key: str
    ) -> None:
        resp = await test_client.patch(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            json={"is_active": False},
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_delete_requires_admin(
        self, test_client: AsyncClient, alerts_read_key: str
    ) -> None:
        resp = await test_client.delete(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_no_auth_returns_401(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.get("/v1/indicator-mappings")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Seeder idempotency (via API inspection)
# ---------------------------------------------------------------------------


class TestSeederIdempotencyViaAPI:
    async def test_system_mappings_count_is_14(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """
        The seeder should create exactly 14 system mappings.
        If more or fewer exist, the seeder has a bug.
        """
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=50",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        total = resp.json()["meta"]["total"]
        assert total == 14, f"Expected 14 system mappings, got {total}"

    async def test_system_mappings_all_normalized_target(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """All system mappings should have extraction_target='normalized'."""
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=50",
            headers=auth_header(api_key),
        )
        for m in resp.json()["data"]:
            assert m["extraction_target"] == "normalized", (
                f"System mapping {m['field_path']} has unexpected extraction_target: "
                f"{m['extraction_target']}"
            )

    async def test_system_mappings_all_active_by_default(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """All system mappings should be active by default."""
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=50",
            headers=auth_header(api_key),
        )
        for m in resp.json()["data"]:
            assert m["is_active"] is True, (
                f"System mapping {m['field_path']} is not active by default"
            )

    async def test_system_mappings_have_null_source_name(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """All system mappings should have source_name=NULL (global)."""
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=50",
            headers=auth_header(api_key),
        )
        for m in resp.json()["data"]:
            assert m["source_name"] is None, (
                f"System mapping {m['field_path']} has non-null source_name: "
                f"{m['source_name']}"
            )

    async def test_expected_system_mapping_fields_present(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """All 14 expected field_paths should be present in system mappings."""
        expected_fields = {
            "src_ip",
            "dst_ip",
            "src_hostname",
            "dst_hostname",
            "file_hash_md5",
            "file_hash_sha256",
            "file_hash_sha1",
            "actor_email",
            "actor_username",
            "dns_query",
            "http_url",
            "http_hostname",
            "email_from",
            "email_reply_to",
        }
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true&page_size=50",
            headers=auth_header(api_key),
        )
        actual_fields = {m["field_path"] for m in resp.json()["data"]}
        assert expected_fields == actual_fields, (
            f"Missing fields: {expected_fields - actual_fields}, "
            f"Extra fields: {actual_fields - expected_fields}"
        )
