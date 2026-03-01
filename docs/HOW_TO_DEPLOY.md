# Calseta AI — Production Deployment Guide

## Overview

Calseta AI is deployed as three Docker Compose services backed by PostgreSQL:

- `api` — FastAPI REST API + admin UI (port 8000)
- `worker` — background job processor
- `mcp` — MCP server (port 8001)
- `db` — PostgreSQL 15 (or bring your own managed Postgres)

The admin UI is compiled during `docker build` (multi-stage: Node.js builds the UI, then the static files are copied into the Python image). It's served by FastAPI at the root path — no separate web server or CDN needed. Access it at `http://your-host:8000`.

All services are stateless except the database. Scale the API and worker horizontally by running multiple replicas — they share no in-memory state.

---

## Prerequisites

- Docker 24+ and Docker Compose v2
- A PostgreSQL 15+ instance (self-hosted or managed: RDS, Azure Database for PostgreSQL, Cloud SQL)
- `pgcrypto` extension enabled on the Postgres instance: `CREATE EXTENSION IF NOT EXISTS pgcrypto;`

---

## Deployment steps

### 1. Pull the latest images

```bash
docker pull ghcr.io/your-org/calseta-api:latest
docker pull ghcr.io/your-org/calseta-worker:latest
docker pull ghcr.io/your-org/calseta-mcp:latest
```

Or use a specific version tag (recommended for production):

```bash
docker pull ghcr.io/your-org/calseta-api:v1.0.0
```

### 2. Configure environment variables

Create a `.env` file (never commit this):

```bash
cp .env.prod.example .env
```

Set all required variables. At minimum:

```bash
# Required
DATABASE_URL=postgresql+asyncpg://calseta:your_password@your-db-host:5432/calseta

# Recommended for production
LOG_FORMAT=json
LOG_LEVEL=INFO
APP_VERSION=v1.0.0

# Security
ENCRYPTION_KEY=your-32-byte-random-key-here
HTTPS_ENABLED=true

# Webhook signing secrets (set for each connected SIEM)
SENTINEL_WEBHOOK_SECRET=your-sentinel-secret
ELASTIC_WEBHOOK_SECRET=your-elastic-secret
SPLUNK_WEBHOOK_SECRET=your-splunk-secret

# Enrichment providers (set the ones you use)
VIRUSTOTAL_API_KEY=your-key
ABUSEIPDB_API_KEY=your-key
```

### 3. Write a production Docker Compose file

```yaml
# docker-compose.prod.yml
services:
  api:
    image: ghcr.io/your-org/calseta-api:v1.0.0
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env.prod
    depends_on:
      db:
        condition: service_healthy

  worker:
    image: ghcr.io/your-org/calseta-worker:v1.0.0
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      db:
        condition: service_healthy

  mcp:
    image: ghcr.io/your-org/calseta-mcp:v1.0.0
    restart: unless-stopped
    ports:
      - "8001:8001"
    env_file: .env.prod
    depends_on:
      db:
        condition: service_healthy

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
```

Skip the `db` service if using a managed Postgres instance — just set `DATABASE_URL` to point at it.

### 4. Initialize the database

Run migrations before starting services:

```bash
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.0.0 \
  alembic upgrade head
```

### 5. Start services

```bash
docker compose -f docker-compose.prod.yml up -d
```

Verify all services are running:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

### 6. Create the first API key

API key management requires `admin` scope, so the very first key must be bootstrapped via CLI:

```bash
docker compose -f docker-compose.prod.yml exec api \
  python -m app.cli.create_api_key --name admin --scopes admin
```

The full API key (`cai_...`) is printed once. **Store it in your secrets manager immediately** — it cannot be retrieved again.

Do not pipe this command's output to a log file or echo it to CI. Treat the key like a password.

Once the admin key exists, create additional keys via the API:

```bash
curl -s -X POST http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "agent-prod", "scopes": ["alerts:read", "alerts:write", "enrichments:read", "workflows:execute"]}' | jq .
```

---

## Updating to a new version

1. Pull new images:
   ```bash
   docker pull ghcr.io/your-org/calseta-api:v1.1.0
   docker pull ghcr.io/your-org/calseta-worker:v1.1.0
   docker pull ghcr.io/your-org/calseta-mcp:v1.1.0
   ```

2. Run migrations before restarting (always do this first):
   ```bash
   docker run --rm \
     --env-file .env.prod \
     ghcr.io/your-org/calseta-api:v1.1.0 \
     alembic upgrade head
   ```

3. Update image tags in `docker-compose.prod.yml` and restart:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. Verify:
   ```bash
   curl http://localhost:8000/health
   ```

---

## Environment variables reference

See `.env.prod.example` for the complete list with descriptions.

### Required

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN (`postgresql+asyncpg://user:pass@host:5432/dbname`) |

### Recommended for production

| Variable | Default | Description |
|---|---|---|
| `APP_VERSION` | `dev` | Set to the release tag (e.g. `v1.0.0`) |
| `LOG_FORMAT` | `json` | Always `json` in production |
| `LOG_LEVEL` | `INFO` | `INFO` or `WARNING` in production |
| `HTTPS_ENABLED` | `false` | Set `true` when behind TLS termination proxy |
| `ENCRYPTION_KEY` | `""` | 32-byte key for encrypting auth configs at rest |
| `TRUSTED_PROXY_COUNT` | `0` | Number of trusted reverse proxies (for real IP extraction) |
| `CORS_ALLOWED_ORIGINS` | `""` | Comma-separated list of allowed CORS origins. Not needed if accessing the UI from the same origin (port 8000) |

### Secrets backends (optional, pick one)

| Variable | Description |
|---|---|
| `AZURE_KEY_VAULT_URL` | Azure Key Vault URL — loads all secrets from Key Vault at startup |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | AWS Secrets Manager secret name |
| `AWS_REGION` | AWS region (required with Secrets Manager) |

---

## Logs

All three services write structured JSON logs to stdout. Route stdout to your log aggregator (CloudWatch, Azure Monitor, Datadog, etc.) via Docker logging drivers:

```yaml
services:
  api:
    logging:
      driver: awslogs
      options:
        awslogs-group: /calseta/api
        awslogs-region: us-east-1
```

---

## Health check

`GET /health` returns `{"status": "ok"}` when the API process is running. This endpoint is unauthenticated and suitable for load balancer health checks.

Note: This checks process health only, not database connectivity. For a database-aware readiness check, use the `/v1/api-keys` endpoint (requires a valid API key) — a 200 response confirms the DB is reachable.

---

## Branch protection (apply manually in GitHub repo settings)

- **Main branch:** require CI to pass before merge; no direct pushes; require linear history (rebase or squash)
- Required status checks: `ci / ci`
- Merge methods: allow squash and rebase only; disable merge commits
