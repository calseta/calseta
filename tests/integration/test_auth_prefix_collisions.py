"""
S17 — API key prefix collision integration tests.

These tests cover the three S17 acceptance scenarios end-to-end against a
real Postgres database via the FastAPI test client:

  1. Two keys sharing the same plaintext prefix — only the bcrypt-matched
     key's scopes drive the auth decision. The other key (with different
     scopes) MUST be rejected on routes that require its sibling's scopes.

  2. ``MultipleResultsFound`` regression — manually inserting two
     ``api_keys`` rows with the same 16-char prefix must not crash the auth
     pipeline. ``GET /v1/agents`` returns 200 for the matching key.

  3. Lab key continuity — the well-known lab key
     ``cai_lab_demo_full_access_key_not_for_prod`` continues to work after
     the prefix-length bump (lab seeder regenerates its prefix on next
     reset; the test mimics a re-seed and asserts auth still works).
"""

from __future__ import annotations

import secrets

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey
from tests.integration.conftest import auth_header

pytestmark = pytest.mark.asyncio


def _make_keys_with_same_prefix(
    prefix: str,
) -> tuple[str, str]:
    """
    Generate two distinct full keys that share ``prefix`` as their first
    16 chars. Each key has its own random suffix so their bcrypt hashes
    are different.
    """
    assert len(prefix) == 16, "Test setup expects a 16-char prefix"
    key_a = prefix + "_" + secrets.token_urlsafe(20)
    key_b = prefix + "_" + secrets.token_urlsafe(20)
    assert key_a != key_b
    return key_a, key_b


async def _insert_api_key(
    db: AsyncSession,
    *,
    plain_key: str,
    scopes: list[str],
    name: str,
) -> APIKey:
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()
    record = APIKey(
        name=name,
        key_prefix=plain_key[:16],
        key_hash=key_hash,
        scopes=scopes,
        is_active=True,
    )
    db.add(record)
    await db.flush()
    return record


# ---------------------------------------------------------------------------
# Acceptance 1: scope-by-prefix collision must NOT grant the wrong scopes
# ---------------------------------------------------------------------------


class TestPrefixCollisionScopeIsolation:
    """Two keys sharing a prefix; only the matched key's scopes count."""

    async def test_low_scope_key_rejected_for_admin_route(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        # Pick a deterministic 16-char prefix shared by both keys.
        shared_prefix = "cai_collide_test"  # 16 chars
        admin_key, low_key = _make_keys_with_same_prefix(shared_prefix)

        await _insert_api_key(
            db_session,
            plain_key=admin_key,
            scopes=["admin"],
            name="collision-admin",
        )
        await _insert_api_key(
            db_session,
            plain_key=low_key,
            scopes=["alerts:read"],
            name="collision-low",
        )

        # Both keys share the first 16 chars but have different bcrypt hashes.
        assert admin_key[:16] == low_key[:16] == shared_prefix

        # /v1/api-keys requires admin. The low-scope key MUST be rejected
        # even though a sibling key sharing the prefix has admin.
        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(low_key),
        )
        assert resp.status_code == 403, resp.text

    async def test_admin_key_accepted_for_admin_route(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        shared_prefix = "cai_collide_acpt"  # 16 chars
        admin_key, low_key = _make_keys_with_same_prefix(shared_prefix)

        await _insert_api_key(
            db_session,
            plain_key=admin_key,
            scopes=["admin"],
            name="collision-admin-2",
        )
        await _insert_api_key(
            db_session,
            plain_key=low_key,
            scopes=["alerts:read"],
            name="collision-low-2",
        )

        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 200, resp.text

    async def test_low_scope_key_accepted_for_its_own_route(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        shared_prefix = "cai_collide_read"  # 16 chars
        admin_key, low_key = _make_keys_with_same_prefix(shared_prefix)

        await _insert_api_key(
            db_session,
            plain_key=admin_key,
            scopes=["admin"],
            name="collision-admin-3",
        )
        await _insert_api_key(
            db_session,
            plain_key=low_key,
            scopes=["alerts:read"],
            name="collision-low-3",
        )

        # The low-scope key has alerts:read; /v1/alerts should return 200.
        resp = await test_client.get(
            "/v1/alerts",
            headers=auth_header(low_key),
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Acceptance 2: MultipleResultsFound regression
# ---------------------------------------------------------------------------


class TestMultipleResultsFoundRegression:
    """
    Two rows with the same 16-char prefix must not crash the auth pipeline.

    Pre-S17 the repository used ``scalar_one_or_none()`` which raised
    ``sqlalchemy.exc.MultipleResultsFound`` when more than one row matched.
    The iterate-and-bcrypt pattern in S17 returns a list and walks
    candidates instead — collisions just mean a few extra bcrypt checks.
    """

    async def test_get_v1_agents_returns_200_with_collision(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        shared_prefix = "cai_mrf_regress1"  # 16 chars
        active_key, dummy_key = _make_keys_with_same_prefix(shared_prefix)

        # The "real" key has agents:read; the colliding row has nothing.
        await _insert_api_key(
            db_session,
            plain_key=active_key,
            scopes=["agents:read"],
            name="mrf-active",
        )
        await _insert_api_key(
            db_session,
            plain_key=dummy_key,
            scopes=["alerts:read"],
            name="mrf-dummy",
        )

        resp = await test_client.get(
            "/v1/agents",
            headers=auth_header(active_key),
        )
        assert resp.status_code == 200, resp.text

    async def test_unknown_key_with_colliding_prefix_rejected(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        """
        A token sharing the prefix but matching no row's bcrypt hash must
        be rejected — iterating candidates can't grant access to a key the
        DB doesn't store.
        """
        shared_prefix = "cai_mrf_regress2"  # 16 chars
        real_key, _ = _make_keys_with_same_prefix(shared_prefix)
        bogus_key = shared_prefix + "_" + secrets.token_urlsafe(20)

        await _insert_api_key(
            db_session,
            plain_key=real_key,
            scopes=["admin"],
            name="mrf-real",
        )

        resp = await test_client.get(
            "/v1/agents",
            headers=auth_header(bogus_key),
        )
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Acceptance 3: lab key continuity after prefix bump
# ---------------------------------------------------------------------------


class TestLabKeyContinuity:
    """
    The well-known lab key continues to authenticate after the 8 → 16
    prefix bump. We mimic the seeder by inserting the lab key with a
    16-char prefix and asserting auth succeeds.
    """

    LAB_KEY = "cai_lab_demo_full_access_key_not_for_prod"

    async def test_lab_key_works_after_reseed(
        self,
        db_session: AsyncSession,
        test_client: AsyncClient,
    ) -> None:
        # Mimic what the lab seeder will do on next ``make lab-reset``:
        # generate the prefix from the first 16 chars of the well-known key.
        await _insert_api_key(
            db_session,
            plain_key=self.LAB_KEY,
            scopes=["admin"],
            name="Lab Demo Key (full access)",
        )

        # /v1/api-keys is admin-gated and a representative read endpoint.
        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(self.LAB_KEY),
        )
        assert resp.status_code == 200, resp.text

    async def test_lab_key_prefix_is_16_chars(self) -> None:
        """The lab key constant is long enough to support a 16-char prefix."""
        assert len(self.LAB_KEY) >= 16
        assert self.LAB_KEY.startswith("cai_")
