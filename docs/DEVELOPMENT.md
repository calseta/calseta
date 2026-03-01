# Calseta AI — Local Development Guide

## Prerequisites

- **Docker** 24+ and **Docker Compose** v2 (`docker compose` not `docker-compose`)
- **Python 3.12+** (for running tests and linting outside of Docker)
- **Node.js 22+** and **npm** (for the admin UI)
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
cp .env.local.example .env
```

The defaults in `.env.local.example` work out of the box with docker compose — no edits needed to get started.

See `.env.prod.example` for the full variable reference with descriptions.

### 3. Start all services

```bash
make dev
```

This starts the DB, runs Alembic migrations, then starts all services:
- `db` — PostgreSQL 15 on port 5432
- `api` — FastAPI app on port 8000 (with hot reload)
- `worker` — procrastinate worker (background jobs)
- `mcp` — MCP server on port 8001

On startup, the API seeds default indicator field mappings and built-in workflows.

### 4. Verify the stack is running

```bash
curl http://localhost:8000/health
# {"status": "ok", "db": "ok", ...}
```

Interactive API docs: http://localhost:8000/docs

### 5. Create your first API key

API key management requires `admin` scope, so the very first key must be bootstrapped via CLI:

```bash
docker compose exec api python -m app.cli.create_api_key \
  --name bootstrap-admin --scopes admin
```

The full API key (`cai_...`) is printed once. **Save it immediately** — it cannot be retrieved again.

Use it in subsequent requests:

```bash
export CALSETA_KEY="cai_your_key_here"

# Verify it works
curl -s -H "Authorization: Bearer $CALSETA_KEY" \
  http://localhost:8000/v1/api-keys | jq .

# Create additional keys via the API
curl -s -X POST -H "Authorization: Bearer $CALSETA_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "scopes": ["alerts:read", "alerts:write", "enrichments:read"]}' \
  http://localhost:8000/v1/api-keys | jq .
```

### Day-to-day usage

```bash
# Full start (migrate + start all services)
make dev

# Quick restart after code changes (skip migration)
make dev-up

# Run migrations manually
docker compose run --rm api alembic upgrade head
```

---

## Admin UI

The admin UI is a React SPA in the `ui/` directory. It communicates with the backend REST API and is served by FastAPI in production.

### Setup

```bash
make ui-install      # Install npm dependencies (first time only)
```

### Development (recommended)

```bash
make ui-dev          # Start Vite dev server on http://localhost:5173
```

This gives you instant hot module replacement (HMR) — changes appear in the browser immediately without a page refresh. The Vite dev server proxies all `/v1/*`, `/health`, and `/docs` requests to the backend at `localhost:8000`, so you need the backend running (`make dev` or `make dev-up` in another terminal).

### Production build

```bash
make ui-build        # Build static files to ui/dist/
```

After building, the UI is served by FastAPI at `http://localhost:8000`. The `_SPAStaticFiles` mount in `app/main.py` handles serving static assets and falling back to `index.html` for client-side routing.

In Docker, the Dockerfile has a multi-stage build that compiles the UI during `docker build` — no manual build step needed.

### Authentication

The UI uses the same API keys as the REST API. When you open the UI, you'll see a login screen where you paste a `cai_` API key. The key is stored in `localStorage` and sent as a `Bearer` token on every request.

To create your first key, use the CLI bootstrap command (see "Create your first API key" above).

### Tech stack

| Layer | Technology |
|---|---|
| Framework | React 19 |
| Build tool | Vite |
| Styling | Tailwind CSS v4 |
| Components | shadcn/ui (Radix UI) |
| Data fetching | TanStack Query |
| Routing | TanStack Router |
| Charts | Recharts |
| Icons | Lucide React |
| Toasts | Sonner |

### Project structure

```
ui/
  public/              # Static assets (logo, etc.)
  src/
    components/        # Shared components (layout, UI primitives)
    hooks/             # TanStack Query hooks for every API entity
    lib/               # API client, auth context, types, utilities
    pages/             # Page components organized by route
      dashboard/       # KPI cards and charts
      alerts/          # Alert list + detail with tabs
      workflows/       # Workflow list + detail + approvals
      settings/        # Detection rules, context docs, sources, agents, API keys
    App.tsx            # Root component (providers, auth gate)
    router.tsx         # Route definitions
    main.tsx           # Entry point
  dist/                # Build output (gitignored)
```

### Making changes

When working on the UI:

1. Run `make ui-dev` for development with hot reload at `localhost:5173`
2. Make sure the backend is running (`make dev-up` in another terminal)
3. Changes to `.tsx` files appear instantly in the browser
4. Run `make ui-build` when you want to test the production build served from FastAPI at `localhost:8000`

---

## Log Viewer (Dozzle)

For a web-based log viewer with search, filter, and regex across all services:

```bash
make dev-logs
```

Then open http://localhost:9999. Dozzle shows real-time logs from all containers with JSON pretty-printing, regex search, and SQL queries (DuckDB).

To start Dozzle alongside an already-running stack:

```bash
docker compose --profile dev-tools up -d dozzle
make logs
```

Dozzle is gated behind a Docker Compose profile — it does **not** start with `make dev` or `docker compose up`.

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
  main.py                # FastAPI app factory + UI static mount
  worker.py              # Worker process entry point
  mcp_server.py          # MCP server entry point
  cli/                   # Management commands (create_api_key, etc.)
  models/                # SQLAlchemy ORM models
  schemas/               # Pydantic request/response schemas
  api/v1/                # Route handlers
  integrations/          # Alert source and enrichment plugins
  queue/                 # Task queue abstraction + backends
  services/              # Business logic
  auth/                  # API key authentication
  seed/                  # Startup data seeders
  middleware/            # FastAPI middleware
ui/                      # Admin UI (React + Vite)
  src/                   # TypeScript source
  dist/                  # Production build output (gitignored)
docs/                    # Guides and integration API notes
tests/                   # pytest test suite
alembic/                 # Database migrations
```

---

## CLI commands

Management commands that operate directly against the database. Run inside the Docker container (or any environment with `DATABASE_URL` set).

| Command | Description |
|---|---|
| `python -m app.cli.create_api_key` | Create an API key (bootstrap the first admin key) |
| `python -m app.cli.list_api_keys` | List all API keys *(not yet implemented)* |
| `python -m app.cli.seed_demo_data` | Seed realistic demo data (detection rules, context docs, alerts) |
| `python -m app.cli.rotate_encryption_key` | Rotate the encryption key *(not yet implemented)* |

### Create API key

```bash
# Admin key (full access)
docker compose exec api python -m app.cli.create_api_key \
  --name bootstrap-admin --scopes admin

# Scoped key for an agent
docker compose exec api python -m app.cli.create_api_key \
  --name my-agent --scopes alerts:read alerts:write enrichments:read workflows:execute

# Key restricted to a single alert source
docker compose exec api python -m app.cli.create_api_key \
  --name sentinel-ingest --scopes alerts:write --allowed-sources sentinel

# Key with expiry
docker compose exec api python -m app.cli.create_api_key \
  --name temp-key --scopes alerts:read --expires-at 2026-12-31T23:59:59Z
```

Valid scopes: `admin`, `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:write`, `workflows:execute`, `agents:read`, `agents:write`

### Seed demo data

Populate the database with realistic detection rules, context documents, and sample alerts from all three source types (Sentinel, Elastic, Splunk). Useful for demos, local development, and testing agent integrations against real-looking data.

```bash
# Full seed — rules, docs, and 9 alerts with enrichment enqueued
docker compose exec api python -m app.cli.seed_demo_data

# Rules and context documents only (no alerts)
docker compose exec api python -m app.cli.seed_demo_data --skip-alerts

# Alerts without enrichment (no worker needed)
docker compose exec api python -m app.cli.seed_demo_data --skip-enrichment
```

**What gets created:**

| Type | Count | Details |
|------|-------|---------|
| Detection rules | 5 | PowerShell execution, brute force, malware hash match, impossible travel, DNS tunneling — each with MITRE mappings and triage documentation |
| Context documents | 3 | General IR playbook (global), escalation matrix (global), phishing response SOP (targeted) |
| Alerts | 9 | 3 Sentinel, 3 Elastic, 3 Splunk — timestamps relative to now so data always looks fresh |

The command is **idempotent** — safe to run multiple times. Detection rules are matched by `(source_name, source_rule_id)` and context documents by title; existing records are skipped. Alerts are always created (they represent new events).

If running without `--skip-enrichment`, make sure the worker is running (`docker compose up worker`) to process the enrichment queue.

---

## Adding a new alert source

See `docs/HOW_TO_ADD_ALERT_SOURCE.md`.

## Adding a new enrichment provider

See `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`.

---

## Environment variables reference

See `.env.local.example` for dev defaults and `.env.prod.example` for the full reference. Key variables for development:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | **Required.** PostgreSQL DSN |
| `LOG_FORMAT` | `json` | `text` for colored local output |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose output |
| `QUEUE_BACKEND` | `postgres` | Task queue backend |
| `QUEUE_CONCURRENCY` | `10` | Worker concurrency |

Set `LOG_FORMAT=text` in your `.env` for human-readable local output instead of JSON.
