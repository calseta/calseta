# Agent Control Plane Integration Tests — Agent Navigation

## What This Does

This directory contains integration tests for the v2 agent control plane. Tests run against a real PostgreSQL database — no mocking of DB queries. Each test phase maps to a control plane feature phase (Phase 1 = managed agent execution, Phase 2 = actions, Phase 4 = budget, Phase 5 = orchestration, etc.).

## Key Files

| File | Responsibility |
|------|---------------|
| `conftest.py` | Fixtures: agent + key creation, enriched alert, auth header helpers |
| `fixtures/mock_alerts.py` | `create_enriched_alert()` — inserts a ready-to-checkout alert directly in DB |
| `fixtures/mock_llm_responses.py` | Canned LLM response sequences for mocking `LLMProviderAdapter.create_message` |
| `test_phase1_managed_agent.py` | Managed agent execution: tool loop, session persistence, budget hard stop, compaction |
| `test_phase1_claude_code_adapter.py` | ClaudeCode subprocess adapter: NDJSON parsing, session_id round-trip |
| `test_phase4_budget.py` | Budget enforcement: monthly cap, per-alert cap, supervisor detection |
| `test_phase5_invocation_poll.py` | Invocation polling: single, parallel, long-poll timeout |
| `test_phase5_orchestration.py` | Full orchestration flow: orchestrator delegates to specialists, results aggregated |

## How to Run

```bash
# Run all control plane integration tests
TEST_DATABASE_URL="postgresql+asyncpg://calseta:calseta@localhost:5432/calseta_test" \
  pytest tests/integration/agent_control_plane/ -v

# Run a specific phase
TEST_DATABASE_URL="..." pytest tests/integration/agent_control_plane/test_phase1_managed_agent.py -v

# Run a single test
TEST_DATABASE_URL="..." pytest tests/integration/agent_control_plane/test_phase4_budget.py::test_monthly_budget_hard_stop -v
```

The `TEST_DATABASE_URL` env var must point to a running test PostgreSQL instance. The Docker Compose `db` service works: `postgresql+asyncpg://calseta:calseta@localhost:5432/calseta_test`.

## The Real DB Rule

**Never mock the database.** These are integration tests. The whole point is to verify behavior against real PostgreSQL — foreign key constraints, ON CONFLICT clauses, SELECT FOR UPDATE locks, and procrastinate queue interactions all require a real DB to test correctly. If you need to test a DB interaction without side effects, use a transaction that rolls back (the root `conftest.py` does this via `db_session` fixture with rollback).

## Conftest Fixtures

### From `conftest.py` (this directory)

| Fixture | Type | What It Provides |
|---------|------|-----------------|
| `agent_with_key` | `tuple[AgentRegistration, str]` | An active agent + its `cak_*` plain API key (bcrypt-hashed in DB) |
| `agent_auth_headers` | `dict[str, str]` | `{"Authorization": "Bearer cak_..."}` for a single test agent |
| `agent_and_auth` | `tuple[AgentRegistration, dict]` | Convenience: agent + headers together |
| `agent_auth_headers_list` | `list[dict[str, str]]` | 10 distinct agent keys for concurrent-checkout tests |
| `enriched_alert` | `Alert` | An alert with `enrichment_status='Enriched'`, `status='Open'`, no assignment |
| `admin_auth_headers` | `dict[str, str]` | Headers using root conftest admin key (scopes=['admin']) |
| `read_auth_headers` | `dict[str, str]` | Headers for a read-only key (agents:read only) |

### From parent `conftest.py` (tests/integration/)

| Fixture | What It Provides |
|---------|-----------------|
| `db_session` | `AsyncSession` — real DB session, rolled back after each test |
| `test_client` | `AsyncClient` — HTTPX async client against the FastAPI app |
| `api_key` | `str` — admin `cai_*` key for operator calls |
| `scoped_api_key` | `Callable[[list[str]], Coroutine[str]]` — factory to create keys with specific scopes |
| `auth_header` | Helper: `auth_header(key)` → `{"Authorization": "Bearer {key}"}` |

### Creating Test Data

Use `_create_agent_with_key(db_session)` directly in a test when you need custom agent attributes:

```python
from tests.integration.agent_control_plane.conftest import _create_agent_with_key

async def test_something(db_session, test_client):
    agent, plain_key = await _create_agent_with_key(
        db_session,
        name="my-test-agent",
        budget_monthly_cents=1000,  # $10 monthly budget
        status="active",
    )
    headers = {"Authorization": f"Bearer {plain_key}"}
    # ... test ...
```

`create_enriched_alert(db_session)` from `fixtures/mock_alerts.py` inserts an alert directly — it bypasses the ingest pipeline entirely. Use this when you need an alert that is:
- `enrichment_status='Enriched'`, `status='Open'`
- Has indicators attached
- Has no existing assignment

## Agent Key vs Operator Key

**Agent keys (`cak_*`):** Required for queue-scoped endpoints. When a `cak_*` key authenticates, `auth.agent_registration_id` is set. The `_get_agent()` helper in route files uses this to scope queries to the calling agent.

**Operator keys (`cai_*`):** Standard human/API keys. No `agent_registration_id` set.

Which endpoints require which:

| Endpoint | Required key type |
|----------|------------------|
| `POST /v1/queue/{uuid}/checkout` | `cak_*` — 403 with operator key |
| `POST /v1/queue/{uuid}/release` | `cak_*` |
| `GET /v1/assignments/mine` | `cak_*` |
| `POST /v1/actions` | `cak_*` |
| `POST /v1/invocations` | `cak_*` with orchestrator agent_type |
| `PATCH /v1/actions/{uuid}` | `cai_*` with AGENTS_WRITE scope |
| `GET /v1/queue` | Either (operator sees all, agent sees eligible) |
| `GET /v1/alerts/{uuid}` | Either |

The auth pattern `auth.agent_registration_id` is the signal. In tests, use `agent_auth_headers` for agent calls and `admin_auth_headers` for operator calls.

## Calling Task Handlers Directly

Procrastinate tasks are defined in `app/queue/registry.py`. In tests, instead of enqueuing and running a worker, import the task function and call it directly:

```python
from app.queue.registry import run_managed_agent_task

# Call the task handler directly — no worker needed
await run_managed_agent_task(
    payload={"agent_id": agent.id, "task_key": "alert:123", "heartbeat_run_id": run.id}
)
```

This is how Phase 1/Phase 2 tests verify execution behavior without starting a procrastinate worker. The task function is a regular async coroutine — calling it directly is safe as long as you pass a valid `db_session`-compatible environment (the task handlers create their own sessions internally via `get_db_session()`).

If the task function requires a DB session argument, pass `db_session` directly. Check the task signature in `registry.py` first.

## Registry Reset Pattern

Some tests modify environment variables or global registries (e.g., enrichment provider registry, source plugin registry). Always reset them before a test that patches env vars:

```python
from app.integrations.enrichment.registry import reset_registry

@pytest.mark.asyncio
async def test_with_custom_provider(monkeypatch, db_session):
    reset_registry()  # Clear any state from previous tests
    monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-key")
    # ... test ...
```

Failure to reset: a test that passed an enrichment provider check may leave the registry in a state that causes the next test to skip enrichment silently.

## Minimal Skeleton — Writing a New Control Plane Test

Every integration test for a new endpoint needs these five things:

```python
# 1. Imports
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# 2. Create test data (agent + alert via conftest fixtures)
@pytest.mark.asyncio
async def test_my_new_phase_endpoint(
    test_client: AsyncClient,
    db_session: AsyncSession,
    agent_and_auth: tuple,           # (AgentRegistration, headers)
    admin_auth_headers: dict,        # operator key headers
    enriched_alert,                  # Alert ready for checkout
):
    agent, agent_headers = agent_and_auth

    # 3. Call endpoint via test_client
    response = await test_client.post(
        f"/v1/queue/{enriched_alert.uuid}/checkout",
        headers=agent_headers,
    )

    # 4. Assert response shape
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["alert_uuid"] == str(enriched_alert.uuid)
    assert data["status"] == "in_progress"

    # 5. Assert DB state via repository (not just response)
    from app.repositories.alert_assignment_repository import AlertAssignmentRepository
    repo = AlertAssignmentRepository(db_session)
    assignment = await repo.get_by_alert_and_agent(enriched_alert.id, agent.id)
    assert assignment is not None
    assert assignment.status == "in_progress"
```

Key rules:
- Use `agent_auth_headers` for agent-scoped endpoints, `admin_auth_headers` for operator endpoints
- Always verify DB state — the response can succeed even if the DB write silently failed
- Use the `enriched_alert` fixture for checkout tests; it's already in the right state
- For tests requiring a specific alert state not provided by `enriched_alert`, use `create_enriched_alert(db_session)` with custom parameters or create the alert row directly

## What Is Not Tested Here

- LLM API calls are always mocked via `mock_llm_responses.py` — no real Anthropic/OpenAI calls in CI
- External enrichment provider HTTP calls (VirusTotal, AbuseIPDB, etc.) — use unit tests with httpx mock transport
- Worker process startup — task handlers are called directly, not via procrastinate worker
