"""
Tests for app/seed/builtin_workflows.py (Chunk 4.5).

All tests are unit-level — no DB required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.seed.builtin_workflows import _WORKFLOWS, seed_builtin_workflows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(*, okta_domain="", okta_token="", entra_tid="", entra_cid="", entra_cs=""):
    cfg = MagicMock()
    cfg.OKTA_DOMAIN = okta_domain
    cfg.OKTA_API_TOKEN = okta_token
    cfg.ENTRA_TENANT_ID = entra_tid
    cfg.ENTRA_CLIENT_ID = entra_cid
    cfg.ENTRA_CLIENT_SECRET = entra_cs
    return cfg


# ---------------------------------------------------------------------------
# Catalog sanity
# ---------------------------------------------------------------------------


def test_workflow_catalog_has_nine_entries():
    assert len(_WORKFLOWS) == 9


def test_five_okta_workflows():
    okta = [w for w in _WORKFLOWS if w.requires_okta]
    assert len(okta) == 5


def test_four_entra_workflows():
    entra = [w for w in _WORKFLOWS if w.requires_entra]
    assert len(entra) == 4


def test_all_names_unique():
    names = [w.name for w in _WORKFLOWS]
    assert len(names) == len(set(names))


def test_all_workflow_codes_pass_ast_validation():
    from app.services.workflow_ast import validate_workflow_code

    for spec in _WORKFLOWS:
        errors = validate_workflow_code(spec.code)
        assert errors == [], f"{spec.name} code failed validation: {errors}"


def test_all_docs_have_required_sections():
    required_headings = [
        "## Description",
        "## When to Use",
        "## Required Secrets",
        "## Expected Outcome",
        "## Error Cases",
    ]
    for spec in _WORKFLOWS:
        for heading in required_headings:
            assert heading in spec.documentation, (
                f"{spec.name} documentation missing '{heading}'"
            )


# ---------------------------------------------------------------------------
# Seeder — Okta credentials present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_okta_active_when_credentials_set():
    """Okta workflows seeded with is_active=True when creds present."""
    cfg = _make_settings(okta_domain="company.okta.com", okta_token="token123")

    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())

    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    calls = repo_mock.upsert_system_workflow.call_args_list
    okta_calls = [c for c in calls if "Okta" in c.kwargs.get("name", "")]
    assert len(okta_calls) == 5
    for c in okta_calls:
        assert c.kwargs["is_active"] is True


@pytest.mark.asyncio
async def test_seed_okta_inactive_when_missing_domain():
    """Okta workflows seeded with is_active=False when OKTA_DOMAIN is missing."""
    cfg = _make_settings(okta_token="token123")  # domain missing

    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())

    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    calls = repo_mock.upsert_system_workflow.call_args_list
    okta_calls = [c for c in calls if "Okta" in c.kwargs.get("name", "")]
    for c in okta_calls:
        assert c.kwargs["is_active"] is False


@pytest.mark.asyncio
async def test_seed_okta_inactive_when_missing_token():
    """Okta workflows seeded with is_active=False when OKTA_API_TOKEN is missing."""
    cfg = _make_settings(okta_domain="company.okta.com")  # token missing

    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())

    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    calls = repo_mock.upsert_system_workflow.call_args_list
    okta_calls = [c for c in calls if "Okta" in c.kwargs.get("name", "")]
    for c in okta_calls:
        assert c.kwargs["is_active"] is False


# ---------------------------------------------------------------------------
# Seeder — Entra credentials present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_entra_active_when_credentials_set():
    """Entra workflows seeded with is_active=True when all creds present."""
    cfg = _make_settings(entra_tid="tid", entra_cid="cid", entra_cs="secret")

    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())

    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    calls = repo_mock.upsert_system_workflow.call_args_list
    entra_calls = [c for c in calls if "Entra" in c.kwargs.get("name", "")]
    assert len(entra_calls) == 4
    for c in entra_calls:
        assert c.kwargs["is_active"] is True


@pytest.mark.asyncio
async def test_seed_entra_inactive_when_partial_credentials():
    """Entra workflows seeded with is_active=False when any cred is missing."""
    cfg = _make_settings(entra_tid="tid", entra_cid="cid")  # client_secret missing

    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())

    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    calls = repo_mock.upsert_system_workflow.call_args_list
    entra_calls = [c for c in calls if "Entra" in c.kwargs.get("name", "")]
    for c in entra_calls:
        assert c.kwargs["is_active"] is False


# ---------------------------------------------------------------------------
# Seeder — total call count and shared fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_calls_upsert_nine_times():
    """Seeder calls upsert_system_workflow exactly 9 times."""
    cfg = _make_settings()
    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())
    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    assert repo_mock.upsert_system_workflow.call_count == 9


@pytest.mark.asyncio
async def test_seed_all_have_indicator_type_account():
    """All seeded workflows have workflow_type='indicator' and indicator_types=['account']."""
    cfg = _make_settings()
    repo_mock = AsyncMock()
    repo_mock.upsert_system_workflow = AsyncMock(return_value=MagicMock())
    db_mock = MagicMock()

    with patch("app.repositories.workflow_repository.WorkflowRepository", return_value=repo_mock):
        await seed_builtin_workflows(db_mock, cfg)

    for c in repo_mock.upsert_system_workflow.call_args_list:
        assert c.kwargs["workflow_type"] == "indicator"
        assert c.kwargs["indicator_types"] == ["account"]
        assert c.kwargs["state"] == "active"
