"""
Integration tests for LLM integration CRUD and adapter routing.

Covers:
  POST   /v1/llm-integrations        create, duplicate-name 409
  GET    /v1/llm-integrations        paginated list
  GET    /v1/llm-integrations/{id}   detail, api_key_ref redaction
  PATCH  /v1/llm-integrations/{id}   field updates, is_default single-default invariant
  DELETE /v1/llm-integrations/{id}   happy-path 204, 409 when in-use by agent
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

_ENDPOINT = "/v1/llm-integrations"

_BASE_PAYLOAD: dict[str, Any] = {
    "name": "test-anthropic-integration",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "api_key_ref": "sk-ant-test-key",
    "cost_per_1k_input_tokens_cents": 3,
    "cost_per_1k_output_tokens_cents": 15,
    "is_default": False,
}


def _make_payload(**overrides: Any) -> dict[str, Any]:
    return {**_BASE_PAYLOAD, **overrides}


class TestLLMIntegrationCRUD:
    async def test_create_integration(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """POST /v1/llm-integrations creates a new integration and returns 201."""
        resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="create-test"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["name"] == "create-test"
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-3-5-sonnet-20241022"
        assert "uuid" in data
        # api_key_ref must never appear in responses
        assert "api_key_ref" not in data
        # api_key_ref_set should be True because we supplied a key
        assert data["api_key_ref_set"] is True

    async def test_create_duplicate_name_fails(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """Creating two integrations with the same name returns 409 DUPLICATE_NAME."""
        payload = _make_payload(name="duplicate-name-test")
        resp1 = await test_client.post(_ENDPOINT, json=payload, headers=admin_auth_headers)
        assert resp1.status_code == 201, resp1.text

        resp2 = await test_client.post(_ENDPOINT, json=payload, headers=admin_auth_headers)
        assert resp2.status_code == 409, resp2.text
        assert resp2.json()["error"]["code"] == "DUPLICATE_NAME"

    async def test_list_integrations(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str], read_auth_headers: dict[str, str]
    ) -> None:
        """GET /v1/llm-integrations returns a paginated list."""
        # Create one integration first so list is non-empty
        await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="list-test"),
            headers=admin_auth_headers,
        )
        resp = await test_client.get(_ENDPOINT, headers=read_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 1

    async def test_get_integration_redacts_api_key_ref(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """GET /v1/llm-integrations/{id} never exposes api_key_ref value, only api_key_ref_set."""
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="redact-test", api_key_ref="super-secret-key"),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        get_resp = await test_client.get(f"{_ENDPOINT}/{uuid}", headers=admin_auth_headers)
        assert get_resp.status_code == 200, get_resp.text
        data = get_resp.json()["data"]

        # Raw key must never be present
        assert "api_key_ref" not in data
        # The boolean sentinel must be True
        assert data["api_key_ref_set"] is True
        # Confirm no value leakage under any key name
        for v in data.values():
            assert v != "super-secret-key"

    async def test_get_integration_api_key_ref_set_false_when_no_key(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """api_key_ref_set is False when no key is set (e.g. env-var-sourced provider)."""
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="no-key-test", api_key_ref=None),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        get_resp = await test_client.get(f"{_ENDPOINT}/{uuid}", headers=admin_auth_headers)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["data"]["api_key_ref_set"] is False

    async def test_patch_integration(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """PATCH /v1/llm-integrations/{id} updates mutable fields."""
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="patch-test"),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        patch_resp = await test_client.patch(
            f"{_ENDPOINT}/{uuid}",
            json={
                "model": "claude-opus-4-5",
                "cost_per_1k_input_tokens_cents": 15,
                "cost_per_1k_output_tokens_cents": 75,
            },
            headers=admin_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        data = patch_resp.json()["data"]
        assert data["model"] == "claude-opus-4-5"
        assert data["cost_per_1k_input_tokens_cents"] == 15
        assert data["cost_per_1k_output_tokens_cents"] == 75

    async def test_delete_integration(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """DELETE /v1/llm-integrations/{id} returns 204 for an unused integration."""
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="delete-test"),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        del_resp = await test_client.delete(f"{_ENDPOINT}/{uuid}", headers=admin_auth_headers)
        assert del_resp.status_code == 204, del_resp.text

        # Confirm gone
        get_resp = await test_client.get(f"{_ENDPOINT}/{uuid}", headers=admin_auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_integration_in_use_fails(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        """DELETE returns 409 INTEGRATION_IN_USE if an agent references it via llm_integration_id."""
        from app.db.models.agent_registration import AgentRegistration
        from app.db.models.llm_integration import LLMIntegration

        # Create the LLM integration row directly in DB so we have its integer id
        llm = LLMIntegration(
            name="in-use-test-llm",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            cost_per_1k_input_tokens_cents=3,
            cost_per_1k_output_tokens_cents=15,
        )
        db_session.add(llm)
        await db_session.flush()
        await db_session.refresh(llm)

        # Create an agent that references the integration via integer FK
        agent = AgentRegistration(
            name="agent-referencing-llm",
            status="active",
            execution_mode="external",
            agent_type="standalone",
            adapter_type="webhook",
            trigger_on_sources=[],
            trigger_on_severities=[],
            timeout_seconds=30,
            retry_count=3,
            llm_integration_id=llm.id,
        )
        db_session.add(agent)
        await db_session.flush()

        # Now try to delete the LLM integration via API — should fail with 409
        llm_uuid = str(llm.uuid)
        del_resp = await test_client.delete(f"{_ENDPOINT}/{llm_uuid}", headers=admin_auth_headers)
        assert del_resp.status_code == 409, del_resp.text
        assert del_resp.json()["error"]["code"] == "INTEGRATION_IN_USE"

    async def test_set_default_integration_unsets_previous(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """
        Setting is_default=True on integration B unsets is_default on integration A.

        The system should always have at most one default.
        """
        # Create first integration and set as default
        first_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="default-first", is_default=True),
            headers=admin_auth_headers,
        )
        assert first_resp.status_code == 201, first_resp.text
        first_uuid = first_resp.json()["data"]["uuid"]
        assert first_resp.json()["data"]["is_default"] is True

        # Create second integration and set as default
        second_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="default-second", is_default=True),
            headers=admin_auth_headers,
        )
        assert second_resp.status_code == 201, second_resp.text
        second_uuid = second_resp.json()["data"]["uuid"]
        assert second_resp.json()["data"]["is_default"] is True

        # First integration must no longer be default
        first_check = await test_client.get(f"{_ENDPOINT}/{first_uuid}", headers=admin_auth_headers)
        assert first_check.status_code == 200
        assert first_check.json()["data"]["is_default"] is False, (
            "First integration should no longer be default after second was set"
        )

        # Second integration should still be default
        second_check = await test_client.get(f"{_ENDPOINT}/{second_uuid}", headers=admin_auth_headers)
        assert second_check.status_code == 200
        assert second_check.json()["data"]["is_default"] is True

    async def test_read_scope_cannot_create(
        self, test_client: AsyncClient, read_auth_headers: dict[str, str]
    ) -> None:
        """agents:read scope cannot create LLM integrations — 403."""
        resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="scope-test"),
            headers=read_auth_headers,
        )
        assert resp.status_code == 403

    async def test_get_nonexistent_returns_404(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        resp = await test_client.get(
            f"{_ENDPOINT}/00000000-0000-0000-0000-000000000000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_usage_endpoint(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """GET /v1/llm-integrations/{id}/usage returns usage aggregate (zeros when no events)."""
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="usage-test"),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        usage_resp = await test_client.get(
            f"{_ENDPOINT}/{uuid}/usage",
            headers=admin_auth_headers,
        )
        assert usage_resp.status_code == 200, usage_resp.text
        data = usage_resp.json()["data"]
        assert data["total_input_tokens"] == 0
        assert data["total_output_tokens"] == 0
        assert data["total_cost_cents"] == 0
        assert data["event_count"] == 0
        assert str(uuid) == str(data["llm_integration_uuid"])

    async def test_patch_name_conflict_returns_409(
        self, test_client: AsyncClient, admin_auth_headers: dict[str, str]
    ) -> None:
        """PATCH that tries to rename to an already-taken name returns 409."""
        await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="name-taken"),
            headers=admin_auth_headers,
        )
        create_resp = await test_client.post(
            _ENDPOINT,
            json=_make_payload(name="name-to-rename"),
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        uuid = create_resp.json()["data"]["uuid"]

        patch_resp = await test_client.patch(
            f"{_ENDPOINT}/{uuid}",
            json={"name": "name-taken"},
            headers=admin_auth_headers,
        )
        assert patch_resp.status_code == 409
        assert patch_resp.json()["error"]["code"] == "DUPLICATE_NAME"
