# Calseta -- Deployment Guide

Complete guide for deploying Calseta, covering local development, production hardening, SIEM integration, and troubleshooting.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Local Development Walkthrough](#2-local-development-walkthrough)
3. [Complete Environment Variables Reference](#3-complete-environment-variables-reference)
4. [Production Deployment](#4-production-deployment)
5. [Production Checklist](#5-production-checklist)
6. [Connecting a SIEM Source](#6-connecting-a-siem-source)
7. [Updating to a New Version](#7-updating-to-a-new-version)
8. [Secrets Management](#8-secrets-management)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Architecture Overview

Calseta runs as four Docker Compose services:

```
FastAPI Server (port 8000)     MCP Server (port 8001)
        |                              |
        +-------------+----------------+
                      |
                 PostgreSQL (port 5432)
                 (also task queue store)
                      |
                 Worker Process
                 (enrichment, webhooks, workflows)
```

| Service  | Process                              | Port | Purpose                                        |
|----------|--------------------------------------|------|------------------------------------------------|
| `api`    | `uvicorn app.main:app`               | 8000 | REST API + admin UI (static SPA)               |
| `worker` | `python -m app.worker`               | --   | Background tasks: enrichment, dispatch, workflows |
| `mcp`    | `python -m app.mcp_server`           | 8001 | MCP server for AI agent consumption            |
| `db`     | PostgreSQL 15-alpine                 | 5432 | Primary data store + task queue (procrastinate) |

All services are stateless except the database. The API and worker share no in-memory state -- only the database. Scale API and worker horizontally by running multiple replicas.

The admin UI is compiled during `docker build` (multi-stage: Node.js builds the UI, then static files are copied into the Python image). It is served by FastAPI at the root path -- no separate web server needed. Access it at `http://your-host:8000`.

---

## 2. Local Development Walkthrough

### Prerequisites

- Docker 24+ and Docker Compose v2
- Git
- (Optional) Python 3.12+ if running outside containers

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/calseta.git
cd calseta
```

### Step 2: Create the `.env` File

```bash
cp .env.local.example .env
```

This sets permissive defaults for local development: relaxed rate limits, human-readable log output, CORS disabled, and a placeholder encryption key.

### Step 3: Start Everything with `make dev`

```bash
make dev
```

This single command runs the following sequence:

1. **Starts PostgreSQL** -- `docker compose up -d db` and waits for `pg_isready`
2. **Runs Alembic migrations** -- `docker compose run --rm api alembic upgrade head` (creates all 15+ tables)
3. **Applies procrastinate schema** -- creates the task queue tables and stored procedures
4. **Starts all services** -- `docker compose up` (api, worker, mcp, db)

Expected output:

```
Waiting for PostgreSQL to be ready...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, ...
...
calseta-api-1     | INFO     calseta_api_starting
calseta-worker-1  | INFO     calseta_worker_starting queues=['enrichment', 'dispatch', 'workflows', 'default']
calseta-worker-1  | INFO     calseta_worker_ready queues=['enrichment', 'dispatch', 'workflows', 'default']
calseta-mcp-1     | INFO     calseta_mcp_starting host=0.0.0.0 port=8001
```

If you only need to restart after code changes (no new migrations):

```bash
make dev-up
```

To include the Dozzle log viewer (accessible at `http://localhost:9999`):

```bash
make dev-logs
```

### Step 4: Verify the Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected response (HTTP 200):

```json
{
  "status": "ok",
  "db": "ok",
  "queue_depth": 0,
  "enrichment_providers": {
    "virustotal": "unconfigured",
    "abuseipdb": "unconfigured",
    "okta": "unconfigured",
    "entra": "unconfigured"
  }
}
```

The health endpoint is unauthenticated. It checks:
- **Database connectivity** -- runs `SELECT 1` with a 2-second timeout
- **Queue depth** -- counts pending procrastinate jobs
- **Enrichment providers** -- reports `configured` or `unconfigured` for each registered provider

If the database is unreachable, the response returns HTTP 503 with `"status": "down"`.

### Step 5: Create the First API Key

The first API key must be bootstrapped via CLI since no authenticated requests are possible yet:

```bash
docker compose exec api python -m app.cli.create_api_key \
  --name bootstrap-admin \
  --scopes admin
```

Expected output:

```
API key created successfully.

  Name:    bootstrap-admin
  UUID:    a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Prefix:  cai_ab12
  Scopes:  admin

  cai_ab12cd34ef56gh78ij90kl12mn34op

Save this key now. It will not be shown again.
```

**Save this key immediately.** The full key (`cai_...`) is shown once and never again. Only the bcrypt hash is stored in the database.

### Step 6: Test an Authenticated Request

```bash
export CALSETA_KEY="cai_ab12cd34ef56gh78ij90kl12mn34op"
curl -s http://localhost:8000/v1/alerts \
  -H "Authorization: Bearer $CALSETA_KEY" | jq .
```

Expected response:

```json
{
  "data": [],
  "meta": {
    "total": 0,
    "page": 1,
    "page_size": 50
  }
}
```

### Step 7: (Optional) Seed Demo Data

To populate the database with realistic detection rules, context documents, and sample alerts from Sentinel, Elastic, and Splunk:

```bash
docker compose exec api python -m app.cli.seed_demo_data
```

Expected output:

```
Demo data seeded successfully.

  Detection rules created: 5
  Context documents created: 3
  Alerts ingested: 9
  Enrichment: enqueued (run the worker to process)
```

Options:
- `--skip-alerts` -- only create detection rules and context documents
- `--skip-enrichment` -- ingest alerts but do not enqueue enrichment tasks

### Step 8: Create Additional API Keys

Once the admin key exists, create scoped keys via the API:

```bash
# Agent key with read + enrichment + workflow execution
curl -s -X POST http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer $CALSETA_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-agent",
    "scopes": ["alerts:read", "alerts:write", "enrichments:read", "workflows:execute"]
  }' | jq .

# Source-restricted ingest key (only accepts alerts from Sentinel)
docker compose exec api python -m app.cli.create_api_key \
  --name sentinel-ingest \
  --scopes alerts:write \
  --allowed-sources sentinel
```

Valid scopes: `admin`, `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:write`, `workflows:execute`, `agents:read`, `agents:write`.

### Step 9: Access the API Documentation

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **Admin UI:** `http://localhost:8000` (served from `ui/dist/` if built)

---

## 3. Complete Environment Variables Reference

All configuration is driven by environment variables. Set them in a `.env` file (never committed to version control) or inject them via your deployment platform.

### Database

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `DATABASE_URL` | string | -- | **Yes** | PostgreSQL connection string. Must use the `asyncpg` driver. Format: `postgresql+asyncpg://user:pass@host:5432/dbname` |

### Application

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `APP_VERSION` | string | `dev` | No | Included in every log line. Set to git tag in CI (e.g. `v1.0.0`) |

### Alert Deduplication

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `ALERT_DEDUP_WINDOW_HOURS` | int | `24` | No | Deduplication window in hours. Alerts with the same fingerprint within this window are deduplicated. Set to `0` to disable |

### MCP Server

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `MCP_HOST` | string | `0.0.0.0` | No | MCP server bind address |
| `MCP_PORT` | int | `8001` | No | MCP server port |

### Logging

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `LOG_LEVEL` | string | `INFO` | No | Minimum log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | string | `json` | No | Output format: `json` (production -- newline-delimited JSON to stdout) or `text` (local dev -- colored human-readable) |

### Task Queue

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `QUEUE_BACKEND` | string | `postgres` | No | Queue backend. Only `postgres` is fully tested in v1. Stubbed: `celery_redis`, `sqs`, `azure_service_bus` |
| `QUEUE_CONCURRENCY` | int | `10` | No | Maximum number of tasks the worker processes in parallel |
| `QUEUE_MAX_RETRIES` | int | `3` | No | Maximum retry attempts for failed tasks |
| `QUEUE_RETRY_BACKOFF_SECONDS` | int | `60` | No | Seconds between retry attempts |

### Security -- Encryption

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `ENCRYPTION_KEY` | string | `""` | **Production: Yes** | Fernet key for encrypting sensitive fields at rest (agent auth headers, source auth configs). Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Platform starts without it but cannot store encrypted secrets |

### Rate Limiting

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `RATE_LIMIT_UNAUTHED_PER_MINUTE` | int | `30` | No | Rate limit for unauthenticated requests (keyed by IP) |
| `RATE_LIMIT_AUTHED_PER_MINUTE` | int | `600` | No | Rate limit for authenticated requests (keyed by API key prefix) |
| `RATE_LIMIT_INGEST_PER_MINUTE` | int | `100` | No | Rate limit for alert ingestion endpoints |
| `RATE_LIMIT_ENRICHMENT_PER_MINUTE` | int | `60` | No | Rate limit for on-demand enrichment requests |
| `RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE` | int | `30` | No | Rate limit for workflow execution requests |
| `TRUSTED_PROXY_COUNT` | int | `0` | No | Number of trusted reverse proxy hops. When > 0, the real client IP is read from `X-Forwarded-For`. Set to `1` for AWS ALB, Azure App Gateway, or a single nginx proxy. **Warning:** incorrect values allow IP spoofing to bypass rate limits |

### Security Headers

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `HTTPS_ENABLED` | bool | `false` | No | Set to `true` when behind TLS termination to enable HSTS header on all responses |
| `SECURITY_HEADER_HSTS_ENABLED` | bool | `true` | No | Enable/disable HSTS header individually (only applies when `HTTPS_ENABLED=true`) |

### CORS

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | string | `""` | No | Comma-separated list of allowed CORS origins (e.g. `https://app.example.com,https://other.example.com`). Leave empty to disable CORS entirely. Only needed if a web UI or external tool accesses the API from a different origin |
| `CORS_ALLOW_ALL_ORIGINS` | bool | `false` | No | **Never set to `true` in production.** Disables all CORS restrictions. Only for local development |

### Request Body Limits

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `MAX_REQUEST_BODY_SIZE_MB` | int | `10` | No | Maximum request body size in MB (enforced before route handlers) |
| `MAX_INGEST_PAYLOAD_SIZE_MB` | int | `5` | No | Maximum alert ingest payload size in MB |

### Webhook Signing Secrets

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `SENTINEL_WEBHOOK_SECRET` | string | `""` | No | HMAC secret for verifying Microsoft Sentinel webhook signatures. Must match the secret configured in Sentinel |
| `ELASTIC_WEBHOOK_SECRET` | string | `""` | No | HMAC secret for verifying Elastic Security webhook signatures |
| `SPLUNK_WEBHOOK_SECRET` | string | `""` | No | HMAC secret for verifying Splunk webhook signatures |

### Cache

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `CACHE_BACKEND` | string | `memory` | No | Cache backend. Only `memory` (in-process with TTL) is supported in v1. `redis` is a future option |

### Enrichment Providers

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `VIRUSTOTAL_API_KEY` | string | `""` | No | VirusTotal v3 API key. Enriches IP, domain, and file hash indicators. Get one at https://www.virustotal.com/gui/my-apikey |
| `ABUSEIPDB_API_KEY` | string | `""` | No | AbuseIPDB v2 API key. Enriches IP indicators with abuse confidence scores. Get one at https://www.abuseipdb.com/account/api |
| `OKTA_DOMAIN` | string | `""` | No | Okta organization domain (e.g. `your-org.okta.com`). Required for Okta enrichment and built-in Okta workflows |
| `OKTA_API_TOKEN` | string | `""` | No | Okta API token. Required with `OKTA_DOMAIN` |
| `ENTRA_TENANT_ID` | string | `""` | No | Microsoft Entra (Azure AD) tenant ID |
| `ENTRA_CLIENT_ID` | string | `""` | No | Microsoft Entra app registration client ID |
| `ENTRA_CLIENT_SECRET` | string | `""` | No | Microsoft Entra app registration client secret |

Enrichment providers are automatically skipped when their API keys are not configured. This is not an error -- the health endpoint reports them as `unconfigured`.

### Persistent Data Volume

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `CALSETA_DATA_DIR` | string | `/data/calseta` | No | Root directory for NDJSON run logs, agent working directories, and workspaces. Must be backed by persistent storage (Docker named volume, EFS, or Azure Files) |
| `AGENT_FILES_DIR` | string | `{CALSETA_DATA_DIR}/agents` | No | Agent working directories. Derived from `CALSETA_DATA_DIR` by default. Each managed agent gets `{AGENT_FILES_DIR}/{uuid}/` |

### Deployment URLs

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `CALSETA_BASE_URL` | string | `http://localhost:8000` | No | Base URL of this Calseta instance. Used for approval callback links and Teams notifier cards |
| `CALSETA_API_BASE_URL` | string | `http://localhost:8000` | No | Public API base URL included in agent webhook payloads and used by agents authenticating via agent API keys (`cak_` prefix) to call back into Calseta (pull-queue, findings, cost reporting) |

### Approval Notifications

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `APPROVAL_NOTIFIER` | string | `none` | No | Approval notification channel: `none` (no notifications), `slack`, or `teams` |
| `APPROVAL_DEFAULT_TIMEOUT_SECONDS` | int | `3600` | No | Default timeout for approval requests (1 hour) |
| `SLACK_BOT_TOKEN` | string | `""` | No | Slack bot OAuth token. Required when `APPROVAL_NOTIFIER=slack` |
| `SLACK_SIGNING_SECRET` | string | `""` | No | Slack signing secret for verifying interactive message callbacks |
| `TEAMS_WEBHOOK_URL` | string | `""` | No | Microsoft Teams incoming webhook URL. Required when `APPROVAL_NOTIFIER=teams` |

### AI / LLM

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | string | `""` | No | Anthropic API key for workflow code generation features |

### Cloud Secrets Backends (Optional)

At most one cloud backend is active. If neither is configured, secrets are read from environment variables and `.env` file only.

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `AZURE_KEY_VAULT_URL` | string | `""` | No | Azure Key Vault URL. When set, all secrets are loaded from Key Vault at startup using `DefaultAzureCredential` |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | string | `""` | No | AWS Secrets Manager secret name. Secret value must be a JSON object whose keys match env var names |
| `AWS_REGION` | string | `""` | No | AWS region. Required when `AWS_SECRETS_MANAGER_SECRET_NAME` is set |

---

## 4. Production Deployment

### Prerequisites

- Docker 24+ and Docker Compose v2
- A PostgreSQL 15+ instance (self-hosted or managed: RDS, Azure Database for PostgreSQL, Cloud SQL)
- `pgcrypto` extension enabled: `CREATE EXTENSION IF NOT EXISTS pgcrypto;`

### Step 1: Pull Images

Use a specific version tag (recommended):

```bash
docker pull ghcr.io/your-org/calseta-api:v1.0.0
docker pull ghcr.io/your-org/calseta-worker:v1.0.0
docker pull ghcr.io/your-org/calseta-mcp:v1.0.0
```

Or build from source:

```bash
docker build --target prod -t calseta .
```

### Step 2: Configure Environment

```bash
cp .env.prod.example .env.prod
```

Edit `.env.prod` with your production values. At minimum:

```bash
DATABASE_URL=postgresql+asyncpg://calseta:your_password@your-db-host:5432/calseta
ENCRYPTION_KEY=<generate-with-fernet>
HTTPS_ENABLED=true
LOG_FORMAT=json
LOG_LEVEL=INFO
APP_VERSION=v1.0.0
TRUSTED_PROXY_COUNT=1
```

### Step 3: Write a Production Compose File

```yaml
# docker-compose.prod.yml
services:
  api:
    image: ghcr.io/your-org/calseta-api:v1.0.0
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env.prod
    volumes:
      - calseta_data:/data/calseta

  worker:
    image: ghcr.io/your-org/calseta-api:v1.0.0
    command: python -m app.worker
    restart: unless-stopped
    env_file: .env.prod
    volumes:
      - calseta_data:/data/calseta

  mcp:
    image: ghcr.io/your-org/calseta-api:v1.0.0
    command: python -m app.mcp_server
    restart: unless-stopped
    ports:
      - "8001:8001"
    env_file: .env.prod
    volumes:
      - calseta_data:/data/calseta

volumes:
  calseta_data:
```

If you are self-hosting PostgreSQL, add the `db` service and its volume:

```yaml
  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: calseta
      POSTGRES_PASSWORD: your_password
      POSTGRES_DB: calseta
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U calseta"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  calseta_data:
```

Skip the `db` service if using a managed PostgreSQL instance -- just set `DATABASE_URL` to point at it.

#### Persistent Data Volume

The `calseta_data` named volume stores NDJSON run logs, agent working directories, and detection-as-code workspaces. It must survive container restarts.

| Platform | Storage | Mount Configuration |
|---|---|---|
| **Docker Compose** (self-hosted) | Named volume `calseta_data` | Defined in `docker-compose.yml` -- no extra config needed. `docker compose down -v` wipes it alongside Postgres (expected for full reset) |
| **AWS ECS** | Amazon EFS | Create an EFS file system, add an access point. Mount in the ECS task definition at `/data/calseta`. All containers in the task share the same mount |
| **Azure Container Apps** | Azure Files | Create an Azure Files share, register as a storage mount in the ACA environment. Mount at `/data/calseta` on each container |
| **Kubernetes** | PersistentVolumeClaim | Create a PVC with `ReadWriteMany` access mode. Mount at `/data/calseta` in all Deployments (api, worker, mcp) |

### Step 4: Initialize the Database

Run Alembic migrations before starting services:

```bash
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.0.0 \
  alembic upgrade head
```

### Step 5: Start Services

```bash
docker compose -f docker-compose.prod.yml up -d
```

Verify:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

### Step 6: Create the Admin API Key

```bash
docker compose -f docker-compose.prod.yml exec api \
  python -m app.cli.create_api_key --name admin --scopes admin
```

**Store the key in your secrets manager immediately.** It is shown once and cannot be retrieved.

---

## 5. Production Checklist

Review every item before going live.

### Encryption Key

- [ ] `ENCRYPTION_KEY` is set to a valid Fernet key (not the dev placeholder)
- [ ] Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] The key is stored in your secrets manager, not in the `.env` file on disk
- [ ] If you are using encrypted agent auth headers or source auth configs, verify encryption works before deploying

### Application Mode

- [ ] `LOG_FORMAT=json` -- structured JSON logs for aggregation
- [ ] `LOG_LEVEL=INFO` or `WARNING` -- never `DEBUG` in production (verbose, may log sensitive data)
- [ ] `APP_VERSION` set to the release tag (e.g. `v1.0.0`)

### Database

- [ ] PostgreSQL 15+ with `pgcrypto` extension enabled
- [ ] `DATABASE_URL` uses `postgresql+asyncpg://` driver prefix
- [ ] Database credentials are rotated and stored in a secrets manager
- [ ] Connection pool tuning: SQLAlchemy defaults (`pool_size=5`, `max_overflow=10`) are suitable for most deployments. For high-throughput setups, increase via SQLAlchemy connection string parameters: `DATABASE_URL=postgresql+asyncpg://...?pool_size=20&max_overflow=40`
- [ ] `pool_pre_ping=True` is enabled by default (reconnects on stale connections)
- [ ] Database backups are configured and tested

### Worker

- [ ] `QUEUE_CONCURRENCY` tuned to expected load (default: `10`). Increase for high-volume alert ingestion. Each concurrent task holds a DB connection
- [ ] `QUEUE_MAX_RETRIES=3` and `QUEUE_RETRY_BACKOFF_SECONDS=60` are appropriate for your enrichment provider SLAs
- [ ] Worker process has `restart: unless-stopped` in the compose file
- [ ] The worker consumes from all four queues: `enrichment`, `dispatch`, `workflows`, `default`

### Security Headers

- [ ] `HTTPS_ENABLED=true` -- enables the Strict-Transport-Security (HSTS) header on all responses
- [ ] TLS termination is handled by a reverse proxy (nginx, ALB, Azure App Gateway, Cloudflare) in front of the API
- [ ] `SECURITY_HEADER_HSTS_ENABLED=true` (default) -- do not disable unless you have a specific reason

### Rate Limiting

- [ ] Production rate limits are set (not the permissive dev values):
  - `RATE_LIMIT_UNAUTHED_PER_MINUTE=30`
  - `RATE_LIMIT_AUTHED_PER_MINUTE=600`
  - `RATE_LIMIT_INGEST_PER_MINUTE=100`
  - `RATE_LIMIT_ENRICHMENT_PER_MINUTE=60`
  - `RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE=30`
- [ ] `TRUSTED_PROXY_COUNT` is set correctly for your proxy chain (0 = direct, 1 = single proxy). Incorrect values allow IP spoofing
- [ ] Rate-limited responses include the `Retry-After` header (automatic)

### CORS

- [ ] `CORS_ALLOW_ALL_ORIGINS=false` -- never `true` in production
- [ ] `CORS_ALLOWED_ORIGINS` is set to only the specific origins that need access (e.g. the admin UI domain), or left empty if no browser-based clients access the API

### Request Body Limits

- [ ] `MAX_REQUEST_BODY_SIZE_MB=10` (default) -- enforced before route handlers
- [ ] `MAX_INGEST_PAYLOAD_SIZE_MB=5` (default) -- prevents oversized alert payloads

### Webhook Signing

- [ ] Unique HMAC secrets generated for each connected SIEM source (`SENTINEL_WEBHOOK_SECRET`, `ELASTIC_WEBHOOK_SECRET`, `SPLUNK_WEBHOOK_SECRET`)
- [ ] Matching secrets configured in each source system
- [ ] Signature verification uses `hmac.compare_digest()` (constant-time comparison, handled automatically)

### Deployment URLs

- [ ] `CALSETA_BASE_URL` set to the externally reachable URL (e.g. `https://calseta.example.com`) -- used for approval callback links
- [ ] `CALSETA_API_BASE_URL` set to the externally reachable API URL -- used in agent webhook payloads and as the base URL for agents authenticating with agent API keys (`cak_` prefix) to pull from the alert queue

### Persistent Data Volume

- [ ] `calseta_data` named volume (or EFS/Azure Files mount) is configured and writable at `/data/calseta`
- [ ] All three services (api, worker, mcp) mount the same volume
- [ ] `CALSETA_DATA_DIR` defaults to `/data/calseta` unless overridden
- [ ] `AGENT_FILES_DIR` is derived as `{CALSETA_DATA_DIR}/agents` (no need to set explicitly unless using a separate mount)

### Monitoring

- [ ] `GET /health` is configured as the load balancer health check target
- [ ] Structured JSON logs are routed to your log aggregator (CloudWatch, Azure Monitor, Datadog, etc.)
- [ ] Alerts set up for `"status": "down"` health check responses (HTTP 503)

---

## 6. Connecting a SIEM Source

### Step-by-Step: Microsoft Sentinel

This walkthrough configures Microsoft Sentinel to send alert webhooks to Calseta.

#### 6.1 Create a Scoped API Key

Create an API key restricted to alert ingestion from Sentinel only:

```bash
docker compose exec api python -m app.cli.create_api_key \
  --name sentinel-prod \
  --scopes alerts:write \
  --allowed-sources sentinel
```

Save the returned key (e.g. `cai_...`).

The `--allowed-sources sentinel` restriction means this key can only ingest alerts tagged as coming from the Sentinel source plugin. It cannot read alerts, execute workflows, or ingest from other sources.

#### 6.2 Generate a Webhook Signing Secret

Generate a strong random secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add it to your `.env` (or secrets manager):

```bash
SENTINEL_WEBHOOK_SECRET=your-generated-secret-here
```

Restart the API service to pick up the new secret.

#### 6.3 Configure Sentinel Automation Rule

In the Azure Portal:

1. Navigate to **Microsoft Sentinel** > **Automation** > **Create** > **Automation rule**
2. Set trigger: **When an incident is created**
3. Add action: **Run playbook** (or use a Logic App with an HTTP action)
4. Configure the HTTP action:
   - **Method:** `POST`
   - **URI:** `https://your-calseta-host/v1/ingest/sentinel`
   - **Headers:**
     - `Authorization: Bearer cai_your_sentinel_key_here`
     - `Content-Type: application/json`
     - `X-Webhook-Signature: <hmac-sha256-signature>` (if using webhook signing)
   - **Body:** The incident JSON payload from Sentinel

The Sentinel source plugin (`app/integrations/sources/sentinel.py`) expects the standard Sentinel incident JSON structure with `properties.title`, `properties.severity`, `Entities`, etc.

#### 6.4 Verify Alert Ingestion

Send a test alert:

```bash
curl -s -X POST https://your-calseta-host/v1/ingest/sentinel \
  -H "Authorization: Bearer $SENTINEL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "/subscriptions/test/providers/Microsoft.SecurityInsights/incidents/test-001",
    "name": "test-001",
    "type": "Microsoft.SecurityInsights/incidents",
    "properties": {
      "title": "Test Alert from Sentinel",
      "description": "Verification test",
      "severity": "Low",
      "status": "New",
      "createdTimeUtc": "2026-03-01T12:00:00.000Z",
      "firstActivityTimeUtc": "2026-03-01T11:55:00.000Z",
      "lastActivityTimeUtc": "2026-03-01T12:00:00.000Z",
      "incidentNumber": 99999,
      "labels": [],
      "additionalData": {"alertsCount": 1, "tactics": []}
    },
    "Entities": [
      {"Type": "ip", "Address": "192.0.2.1"}
    ]
  }'
```

Expected response (HTTP 202):

```json
{
  "data": {
    "alert_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "queued",
    "is_duplicate": false,
    "duplicate_count": null
  },
  "meta": {}
}
```

Verify the alert was stored:

```bash
curl -s http://your-calseta-host/v1/alerts \
  -H "Authorization: Bearer $ADMIN_KEY" | jq '.data[0].title'
```

Expected: `"Test Alert from Sentinel"`

#### 6.5 Connecting Other Sources

The same pattern applies for Elastic Security and Splunk:

| Source | Ingest Endpoint | Webhook Secret Env Var | Payload Format |
|---|---|---|---|
| Sentinel | `POST /v1/ingest/sentinel` | `SENTINEL_WEBHOOK_SECRET` | Sentinel incident JSON |
| Elastic | `POST /v1/ingest/elastic` | `ELASTIC_WEBHOOK_SECRET` | Elastic Security alert JSON (Kibana format) |
| Splunk | `POST /v1/ingest/splunk` | `SPLUNK_WEBHOOK_SECRET` | Splunk alert action payload (`result`, `sid`, `search_name`) |
| Generic | `POST /v1/alerts` | -- (API key auth only) | `{"source_name": "...", "payload": {...}}` |

---

## 7. Updating to a New Version

1. **Pull new images:**

   ```bash
   docker pull ghcr.io/your-org/calseta-api:v1.1.0
   ```

2. **Run migrations before restarting** (always do this first):

   ```bash
   docker run --rm \
     --env-file .env.prod \
     ghcr.io/your-org/calseta-api:v1.1.0 \
     alembic upgrade head
   ```

3. **Update image tags** in `docker-compose.prod.yml` and restart:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. **Verify:**

   ```bash
   curl http://localhost:8000/health
   ```

---

## 8. Secrets Management

### Default: Environment Variables

By default, all secrets are read from environment variables or a `.env` file. This requires no external dependencies and is compatible with `docker compose up` for self-hosters.

### Azure Key Vault

Set `AZURE_KEY_VAULT_URL` to activate. Uses `DefaultAzureCredential` (supports Managed Identity, workload identity, and the full Azure credential chain).

```bash
AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/
```

Install the Azure extras: `pip install calseta[azure]`

Azure Key Vault secret names use hyphens by convention. Calseta maps them back to underscores and uppercases the key (e.g. Key Vault secret `database-url` maps to env var `DATABASE_URL`).

### AWS Secrets Manager

Set `AWS_SECRETS_MANAGER_SECRET_NAME` and `AWS_REGION` to activate. Uses the standard AWS credential chain (IAM role, instance profile, env vars).

```bash
AWS_SECRETS_MANAGER_SECRET_NAME=calseta/production
AWS_REGION=us-east-1
```

The secret value must be a JSON object whose keys match env var names:

```json
{
  "DATABASE_URL": "postgresql+asyncpg://...",
  "ENCRYPTION_KEY": "...",
  "VIRUSTOTAL_API_KEY": "..."
}
```

Install the AWS extras: `pip install calseta[aws]`

### Priority Order

```
Azure Key Vault  (if AZURE_KEY_VAULT_URL set)
   |
AWS Secrets Manager  (if AWS_SECRETS_MANAGER_SECRET_NAME set)
   |
Environment variables
   |
.env file
   |
Defaults
```

Only one cloud backend is active at a time. If neither is configured, the Azure and AWS SDKs are never imported -- no startup penalty for self-hosters. A structured log line at startup always indicates the active source:

```json
{"event": "secrets_source=environment", "level": "info", "service": "api"}
```

---

## 9. Troubleshooting

### Reading Structured Logs

All three processes (api, worker, mcp) write structured logs to stdout.

**JSON format (production):** Each line is a complete JSON object:

```json
{"timestamp": "2026-03-01T12:00:00Z", "level": "info", "service": "api", "version": "v1.0.0", "event": "request_completed", "request_id": "abc-123", "status_code": 200, "method": "GET", "path": "/v1/alerts"}
```

**Text format (local dev):** Colored, human-readable output:

```
2026-03-01T12:00:00Z [info     ] request_completed              request_id=abc-123 status_code=200 method=GET path=/v1/alerts
```

Key fields to look for:
- `request_id` -- correlates all log lines within a single HTTP request
- `task_id` / `task_name` -- correlates worker task execution logs
- `service` -- identifies which process (`api`, `worker`, `mcp`) emitted the log
- `error` -- present on error-level log lines with the exception message

### Common Issues

#### Database Connection Failures

**Symptom:** Health endpoint returns HTTP 503 with `"db": "error"`. API returns 500 errors.

**Diagnosis:**

```bash
# Check if PostgreSQL is reachable
docker compose exec db pg_isready -U postgres

# Check API logs for connection errors
docker compose logs api | grep -i "db\|database\|connect"
```

**Common causes:**
- `DATABASE_URL` has wrong host, port, or credentials
- Docker Compose `db` service is not healthy yet (check `docker compose ps`)
- PostgreSQL `max_connections` exhausted -- increase in `postgresql.conf` or reduce `QUEUE_CONCURRENCY`
- Missing `pgcrypto` extension -- run `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
- Using `postgresql://` instead of `postgresql+asyncpg://` in `DATABASE_URL`

#### Worker Not Processing Tasks

**Symptom:** Alerts are ingested (202 returned) but indicators are never enriched. Queue depth grows on `/health`.

**Diagnosis:**

```bash
# Check if worker is running
docker compose ps worker

# Check worker logs
docker compose logs worker | tail -50

# Check queue depth via health endpoint
curl -s http://localhost:8000/health | jq '.queue_depth'
```

**Common causes:**
- Worker container not running or crashed -- check `docker compose ps`
- Worker cannot connect to database (same `DATABASE_URL` issues as above)
- Procrastinate schema not applied -- run `docker compose run --rm api python -c "$(cat <<'EOF'
import asyncio
from app.queue.registry import procrastinate_app
async def _apply():
    async with procrastinate_app.open_async():
        await procrastinate_app.schema_manager.apply_schema_async()
asyncio.run(_apply())
EOF
)"`
- `QUEUE_CONCURRENCY=0` -- must be > 0

#### Enrichment Not Working

**Symptom:** Alerts are enriched but all indicators remain `malice: Pending`. Enrichment results are empty.

**Diagnosis:**

```bash
# Check which providers are configured
curl -s http://localhost:8000/health | jq '.enrichment_providers'

# Check worker logs for enrichment errors
docker compose logs worker | grep -i "enrich"
```

**Common causes:**
- Enrichment provider API keys not set -- check the health endpoint's `enrichment_providers` section. `unconfigured` means the key is empty
- API key invalid or expired -- the provider returns an error, logged by the worker
- Rate limited by the external provider -- check worker logs for 429 responses
- Network connectivity from the worker container to external APIs is blocked (firewall, proxy)

#### Authentication Failures

**Symptom:** API returns `401 Unauthorized` on requests with a valid-looking key.

**Diagnosis:**

```bash
# Check API logs for auth failure details
docker compose logs api | grep -i "auth\|unauthorized\|401"
```

**Common causes:**
- API key has wrong or missing `Authorization: Bearer` prefix
- API key was created with insufficient scopes -- check the key's scopes against the endpoint requirements
- API key has expired (`expires_at` was set and has passed)
- Key was created with `--allowed-sources` and you are calling an endpoint for a different source
- Mistyped key -- only the 8-character prefix is stored for display; the full key cannot be recovered

#### Encryption Key Errors

**Symptom:** `ValueError: ENCRYPTION_KEY is not a valid Fernet key` when creating source integrations or agent registrations.

**Fix:** Generate a valid Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set this as your `ENCRYPTION_KEY` and restart services. The dev placeholder in `.env.local.example` is not a valid Fernet key and will fail if you attempt to encrypt.

#### MCP Server Port Conflict

**Symptom:** MCP server fails to start with `OSError: [Errno 48] Address already in use`.

**Fix:** Either stop the process using port 8001, or set a different port:

```bash
MCP_PORT=8002
```

#### Migrations Fail

**Symptom:** `alembic upgrade head` fails with table-already-exists or column-not-found errors.

**Diagnosis:**

```bash
# Check current migration state
docker compose run --rm api alembic current

# Check migration history
docker compose run --rm api alembic history --verbose
```

**Common causes:**
- Database was modified outside of Alembic (manual schema changes)
- Running migrations against the wrong database (check `DATABASE_URL`)
- Incomplete previous migration -- check `alembic_version` table in the database

#### Startup Seed Warnings

**Symptom:** API starts but logs `startup_seed_failed` warning.

This is non-fatal. The API starts and serves requests, but system indicator field mappings or built-in workflows may be missing. The warning includes a hint:

```json
{"event": "startup_seed_failed", "error": "...", "hint": "Indicator field mappings or built-in workflows may be missing"}
```

**Common cause:** Migrations have not been run (tables do not exist yet). Run `alembic upgrade head` and restart.

### Health Endpoint Reference

`GET /health` (unauthenticated) returns:

| Field | Type | Description |
|---|---|---|
| `status` | string | `ok` (all checks passed) or `down` (database unreachable) |
| `db` | string | `ok` or `error` |
| `queue_depth` | int | Number of pending tasks in the procrastinate queue |
| `enrichment_providers` | object | Map of provider name to `configured` or `unconfigured` |

HTTP status: 200 when `status=ok`, 503 when `status=down`.

Each subsystem check runs with a 2-second `asyncio.wait_for` timeout, so the health endpoint always responds within a few seconds even if a check hangs.

---

## Appendix: CLI Commands Reference

| Command | Description |
|---|---|
| `python -m app.cli.create_api_key --name <name> --scopes <scopes...>` | Create an API key. Scopes: `admin`, `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:write`, `workflows:execute`, `agents:read`, `agents:write` |
| `python -m app.cli.create_api_key --name <name> --scopes <scopes...> --allowed-sources <sources...>` | Create a source-restricted API key |
| `python -m app.cli.create_api_key --name <name> --scopes <scopes...> --expires-at 2026-12-31T23:59:59Z` | Create an expiring API key |
| `python -m app.cli.seed_demo_data` | Seed database with realistic demo data (5 detection rules, 3 context documents, 9 sample alerts) |
| `python -m app.cli.seed_demo_data --skip-alerts` | Seed only detection rules and context documents |
| `python -m app.cli.seed_demo_data --skip-enrichment` | Seed alerts without triggering enrichment |

All CLI commands can be run inside Docker:

```bash
docker compose exec api python -m app.cli.create_api_key --name admin --scopes admin
docker compose exec api python -m app.cli.seed_demo_data
```

---

## Appendix: Makefile Targets

| Target | Description |
|---|---|
| `make dev` | Full startup: build, wait for DB, migrate, apply queue schema, start all services |
| `make dev-up` | Quick restart (skip migration) |
| `make dev-logs` | Start all services + Dozzle log viewer at `http://localhost:9999` |
| `make logs` | Open Dozzle in browser |
| `make test` | Run pytest test suite |
| `make lint` | Run ruff linter |
| `make typecheck` | Run mypy type checker |
| `make migrate` | Apply pending Alembic migrations |
| `make ci` | Run lint + typecheck + test (same as GitHub Actions) |
| `make build` | Build production Docker image |
| `make ui-install` | Install UI dependencies |
| `make ui-dev` | Start UI dev server (port 5173, proxies API to 8000) |
| `make ui-build` | Build UI for production |
