# Calseta AI — Local Development Guide

## Prerequisites

- **Docker** 24+ and **Docker Compose** v2 (`docker compose` not `docker-compose`)
- **Python 3.12+** (for running tests and linting outside of Docker)
- **uv** (recommended Python package manager) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **make**

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/calseta.git
cd calseta
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and set the required variables. Minimum required for local dev:

```bash
DATABASE_URL=postgresql+asyncpg://calseta:calseta@localhost:5432/calseta
```

All other variables have safe defaults. See `.env.example` for the full list with descriptions.

### 3. Start all services

```bash
make dev
# or: docker compose up
```

This starts:
- `db` — PostgreSQL 15 on port 5432
- `api` — FastAPI app on port 8000
- `worker` — procrastinate worker (background jobs)
- `mcp` — MCP server on port 8001

On first boot, Alembic migrations run automatically and the system seeds the default indicator field mappings.

### 4. Create your first API key

```bash
curl -s -X POST http://localhost:8000/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "dev-key", "scopes": ["admin"]}' | jq .
```

The full API key is returned once. Save it — it cannot be retrieved again.

Use it in subsequent requests:

```bash
curl -s http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer cai_your_key_here" | jq .
```

### 5. Verify the API is running

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

Interactive API docs: http://localhost:8000/docs

---

## Running tests

Tests require a running PostgreSQL instance. The easiest way is to start just the database:

```bash
docker compose up db -d
```

Then run the test suite:

```bash
DATABASE_URL=postgresql+asyncpg://calseta:calseta@localhost:5432/calseta uv run pytest tests/ -v
# or via make:
DATABASE_URL=postgresql+asyncpg://calseta:calseta@localhost:5432/calseta make test
```

Before running tests, apply migrations to the test database:

```bash
DATABASE_URL=postgresql+asyncpg://calseta:calseta@localhost:5432/calseta make migrate
```

---

## Linting and type checking

```bash
make lint        # ruff
make typecheck   # mypy
make ci          # lint + typecheck + test (same as GitHub Actions)
```

These run directly with whatever Python/tools are in your environment. If using `uv`:

```bash
uv run make lint
uv run make typecheck
```

---

## Project structure

```
app/
  config.py              # Settings from env vars
  main.py                # FastAPI app factory
  worker.py              # Worker process entry point
  mcp_server.py          # MCP server entry point
  models/                # SQLAlchemy ORM models
  schemas/               # Pydantic request/response schemas
  api/v1/                # Route handlers
  integrations/          # Alert source and enrichment plugins
  queue/                 # Task queue abstraction + backends
  services/              # Business logic
  auth/                  # API key authentication
  seed/                  # Startup data seeders
  middleware/            # FastAPI middleware
docs/                    # Guides and integration API notes
tests/                   # pytest test suite
alembic/                 # Database migrations
```

---

## Adding a new alert source

See `docs/HOW_TO_ADD_ALERT_SOURCE.md`.

## Adding a new enrichment provider

See `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`.

---

## Environment variables reference

See `.env.example` for the full list. Key variables for development:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | **Required.** PostgreSQL DSN |
| `LOG_FORMAT` | `json` | `text` for colored local output |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose output |
| `QUEUE_BACKEND` | `postgres` | Task queue backend |
| `QUEUE_CONCURRENCY` | `10` | Worker concurrency |

Set `LOG_FORMAT=text` in your `.env` for human-readable local output instead of JSON.
