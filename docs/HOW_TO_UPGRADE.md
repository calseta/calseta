# Calseta AI -- Version Upgrade Guide

Complete procedure for upgrading a Calseta AI deployment to a new version, including pre-upgrade preparation, step-by-step execution, rollback, zero-downtime guidance, and post-upgrade verification.

---

## Table of Contents

1. [Pre-Upgrade Checklist](#1-pre-upgrade-checklist)
2. [Step-by-Step Upgrade Procedure](#2-step-by-step-upgrade-procedure)
3. [Rollback Procedure](#3-rollback-procedure)
4. [Zero-Downtime Upgrade Guidance](#4-zero-downtime-upgrade-guidance)
5. [Version Compatibility Matrix](#5-version-compatibility-matrix)
6. [Post-Upgrade Smoke Test Checklist](#6-post-upgrade-smoke-test-checklist)

---

## 1. Pre-Upgrade Checklist

Complete every item before starting the upgrade.

### 1.1 Read the Changelog

Read the release notes for the target version on the [GitHub Releases page](https://github.com/your-org/calseta/releases). Pay attention to:

- **Breaking API changes** -- endpoints renamed, removed, or with changed request/response shapes
- **New required environment variables** -- variables that must be set before the new version starts
- **Database migrations included** -- whether the release includes schema changes and whether any are destructive (column drops, type changes)
- **Deprecated features** -- features that still work but will be removed in a future version

### 1.2 Note the Current Version

Record the version you are currently running. This is essential for rollback.

```bash
# Check the running image tag
docker compose -f docker-compose.prod.yml ps --format '{{.Image}}'

# Check the version reported by the API (uses APP_VERSION env var)
curl -s http://localhost:8000/docs | grep -o '"version":"[^"]*"'

# Check the current database migration revision
docker compose -f docker-compose.prod.yml run --rm api alembic current
```

Record all three values:

```
Image tag:          v1.0.0
APP_VERSION:        v1.0.0
Alembic revision:   0003 (head)
```

### 1.3 Verify Current Health

Confirm the deployment is healthy before upgrading. Do not upgrade a broken deployment -- fix it first.

```bash
curl -s http://localhost:8000/health | jq .
```

Expected output:

```json
{
  "status": "ok",
  "db": "ok",
  "queue_depth": 0,
  "enrichment_providers": {
    "virustotal": "configured",
    "abuseipdb": "configured",
    "okta": "unconfigured",
    "entra": "unconfigured"
  }
}
```

Verify:
- `status` is `ok`
- `db` is `ok`
- `queue_depth` is `0` or near `0` (a large queue means the worker is behind -- let it catch up before upgrading)

### 1.4 Back Up the Database

**This is mandatory for production upgrades.** A database backup is the only guaranteed rollback path if a migration causes data loss or corruption.

**pg_dump (recommended for most deployments):**

```bash
# Custom format (compressed, supports selective restore)
pg_dump \
  --host=your-db-host \
  --port=5432 \
  --username=calseta \
  --dbname=calseta \
  --format=custom \
  --file=calseta_backup_$(date +%Y%m%d_%H%M%S).dump

# Plain SQL format (human-readable, useful for inspection)
pg_dump \
  --host=your-db-host \
  --port=5432 \
  --username=calseta \
  --dbname=calseta \
  --format=plain \
  --file=calseta_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Docker Compose (self-hosted PostgreSQL):**

```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U calseta -d calseta -Fc \
  > calseta_backup_$(date +%Y%m%d_%H%M%S).dump
```

**Managed database services:**

- **AWS RDS:** Create a manual snapshot from the RDS console or CLI: `aws rds create-db-snapshot --db-instance-identifier calseta --db-snapshot-identifier calseta-pre-upgrade-$(date +%Y%m%d)`
- **Azure Database for PostgreSQL:** Create a backup from the Azure portal or CLI: `az postgres flexible-server backup create --name calseta-pre-upgrade --resource-group your-rg --server-name your-server`
- **Cloud SQL:** `gcloud sql backups create --instance=calseta`

Verify the backup is readable:

```bash
# Custom format: list contents
pg_restore --list calseta_backup_20260302_120000.dump | head -20

# Plain SQL format: check file is non-empty and starts with SQL
head -5 calseta_backup_20260302_120000.sql
```

### 1.5 Review Migration Changes

Check what schema changes the new version introduces. Download or pull the new image and inspect the migration files:

```bash
# List migrations in the new image
docker run --rm ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic history --verbose
```

Compare against your current revision (from step 1.2). If the new version includes migrations that drop columns, rename tables, or change column types, plan for a maintenance window (see [Section 4](#4-zero-downtime-upgrade-guidance)).

### 1.6 Check for New Environment Variables

Review the release notes for any new required or recommended environment variables. Add them to your `.env.prod` file or secrets manager before starting the upgrade.

---

## 2. Step-by-Step Upgrade Procedure

### Step 1: Pull the New Images

```bash
# Pull the specific version (recommended)
docker pull ghcr.io/your-org/calseta-api:v1.1.0

# If you use separate images per service:
docker pull ghcr.io/your-org/calseta-worker:v1.1.0
docker pull ghcr.io/your-org/calseta-mcp:v1.1.0
```

If building from source:

```bash
git fetch origin
git checkout v1.1.0
docker build --target prod -t calseta .
```

### Step 2: Run Database Migrations FIRST

**Always run migrations before starting the new application version.** The new code may depend on schema changes that do not exist yet. The migration command must use the **new** image (which contains the new migration files) against the **existing** database.

```bash
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head
```

If using Docker Compose networking (self-hosted database):

```bash
docker compose -f docker-compose.prod.yml run --rm api \
  alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, add new_feature_table
```

If no new migrations exist, you will see no "Running upgrade" lines -- this is normal.

**If the migration fails:** Do not proceed. See [Section 3: Rollback Procedure](#3-rollback-procedure). The database has not been modified (Alembic runs migrations inside a transaction -- on failure, it rolls back automatically).

For full migration details, see [HOW_TO_RUN_MIGRATIONS.md](HOW_TO_RUN_MIGRATIONS.md).

### Step 3: Update Image Tags and Restart Services

Update the image tags in your `docker-compose.prod.yml`:

```yaml
services:
  api:
    image: ghcr.io/your-org/calseta-api:v1.1.0
    # ...
  worker:
    image: ghcr.io/your-org/calseta-api:v1.1.0
    # ...
  mcp:
    image: ghcr.io/your-org/calseta-api:v1.1.0
    # ...
```

Then restart all services:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Docker Compose will detect the image change and recreate the containers. The `db` service (if self-hosted) is unaffected because its image tag has not changed.

### Step 4: Verify the Upgrade

```bash
# Health check
curl -s http://localhost:8000/health | jq .

# Confirm the new version is running
docker compose -f docker-compose.prod.yml ps --format '{{.Image}}'

# Confirm the migration revision matches the new version
docker compose -f docker-compose.prod.yml run --rm api alembic current
```

### Step 5: Run Smoke Tests

Follow the full [Post-Upgrade Smoke Test Checklist](#6-post-upgrade-smoke-test-checklist) to verify all subsystems are functioning.

---

## 3. Rollback Procedure

If the upgrade causes issues, follow these steps to return to the previous working state.

### 3.1 Stop the New Services

```bash
docker compose -f docker-compose.prod.yml down
```

This stops and removes all application containers. The database service (and its data volume) remains intact.

### 3.2 Choose a Rollback Strategy

There are two rollback strategies. Choose based on the type of migration that was applied.

#### Strategy A: Alembic Downgrade (Preferred When Safe)

Use this when the new version's migrations were **additive only** -- creating new tables, adding nullable columns, adding indexes. No data has been lost.

```bash
# Roll back to the previous migration revision (e.g., 0003)
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic downgrade 0003
```

Then redeploy the previous version (step 3.3).

**When Alembic downgrade is safe:**
- Migration only added new tables or columns
- Migration only created indexes
- No data was written to the new columns/tables (or that data is expendable)

**When Alembic downgrade is NOT safe:**
- Migration dropped columns, tables, or constraints (data is already gone)
- Migration changed column types and existing data no longer fits the original type
- Migration included data transformations that are not reversible
- Significant production data was written to new schema structures

For full details on migration rollback, see [HOW_TO_RUN_MIGRATIONS.md](HOW_TO_RUN_MIGRATIONS.md), Section 4.

#### Strategy B: Full Database Restore (When Downgrade Is Unsafe)

Use this when migrations were destructive or significant data was written to new schema structures.

**Restore from custom-format backup:**

```bash
# Drop and recreate the database
psql -h your-db-host -U postgres -c "DROP DATABASE calseta;"
psql -h your-db-host -U postgres -c "CREATE DATABASE calseta OWNER calseta;"
psql -h your-db-host -U postgres -d calseta -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# Restore the backup
pg_restore \
  --host=your-db-host \
  --port=5432 \
  --username=calseta \
  --dbname=calseta \
  --no-owner \
  --clean \
  --if-exists \
  calseta_backup_20260302_120000.dump
```

**Restore from plain SQL backup:**

```bash
psql -h your-db-host -U postgres -c "DROP DATABASE calseta;"
psql -h your-db-host -U postgres -c "CREATE DATABASE calseta OWNER calseta;"
psql -h your-db-host -U postgres -d calseta -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql -h your-db-host -U calseta -d calseta < calseta_backup_20260302_120000.sql
```

**Docker Compose (self-hosted PostgreSQL):**

```bash
# Stop all services
docker compose -f docker-compose.prod.yml down

# Restore into the running database container
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U calseta -d calseta < calseta_backup_20260302_120000.sql
```

**Managed database services:**
- **AWS RDS:** Restore from the manual snapshot taken in step 1.4
- **Azure:** Restore from the backup created in step 1.4
- **Cloud SQL:** Restore from the backup created in step 1.4

### 3.3 Redeploy the Previous Version

Update `docker-compose.prod.yml` back to the previous image tag:

```yaml
services:
  api:
    image: ghcr.io/your-org/calseta-api:v1.0.0
    # ...
```

Start the services:

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 3.4 Verify the Rollback

```bash
# Health check
curl -s http://localhost:8000/health | jq .

# Confirm the old version is running
docker compose -f docker-compose.prod.yml ps --format '{{.Image}}'

# Confirm the migration revision matches the old version
docker compose -f docker-compose.prod.yml run --rm api alembic current
```

Run the [Post-Upgrade Smoke Test Checklist](#6-post-upgrade-smoke-test-checklist) again to confirm the deployment is fully functional.

---

## 4. Zero-Downtime Upgrade Guidance

### 4.1 Migration-First Approach

The standard Calseta upgrade procedure runs migrations before restarting services. This is the key to minimizing downtime:

```
1. Run migrations (new image, existing database)  ← old services still running
2. Restart services with new image                 ← brief restart window
```

During step 1, the old application version continues serving traffic against the database. This is safe as long as the migrations are **backward-compatible** -- the old code can still function with the new schema.

### 4.2 When Zero-Downtime Is Safe (Additive Migrations)

Migrations are backward-compatible (and zero-downtime safe) when they only perform additive changes:

- **Adding new tables** -- the old code does not reference them
- **Adding nullable columns** -- the old code ignores them (SQLAlchemy does not fail on extra columns)
- **Adding indexes** -- improves performance but does not change behavior
- **Adding new enum values** -- the old code never writes or reads the new values

In this case, the upgrade procedure is:

```bash
# 1. Run migrations while old services are still running
docker run --rm --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head

# 2. Rolling restart: update one service at a time
docker compose -f docker-compose.prod.yml up -d --no-deps api
docker compose -f docker-compose.prod.yml up -d --no-deps worker
docker compose -f docker-compose.prod.yml up -d --no-deps mcp
```

The brief gap between each container restart is the only downtime -- typically under 5 seconds per service.

### 4.3 When a Maintenance Window Is Required (Destructive Migrations)

A maintenance window is required when migrations are **not** backward-compatible:

- **Dropping columns or tables** -- the old code references them and will crash
- **Renaming columns or tables** -- the old code uses the old names
- **Changing column types** -- the old code may not handle the new type
- **Adding NOT NULL constraints to existing columns** -- existing NULL values cause the migration to fail unless a default or backfill is included
- **Data migrations** -- transforming existing data in-place

In this case:

```bash
# 1. Stop all services (maintenance window begins)
docker compose -f docker-compose.prod.yml down

# 2. Run migrations
docker run --rm --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head

# 3. Start services with new version (maintenance window ends)
docker compose -f docker-compose.prod.yml up -d
```

The release notes will always indicate whether a maintenance window is required.

### 4.4 Worker Drain: Graceful Task Completion

Before stopping the worker during an upgrade, allow it to finish processing in-flight tasks. The procrastinate worker handles `SIGTERM` gracefully -- it stops accepting new tasks and finishes the current ones before exiting.

```bash
# Send SIGTERM to the worker (Docker Compose does this automatically on 'down')
docker compose -f docker-compose.prod.yml stop worker

# Wait for the worker to exit (default Docker stop timeout is 10 seconds)
# If tasks take longer, increase the timeout:
docker compose -f docker-compose.prod.yml stop -t 60 worker
```

After the worker stops:

1. Check that no tasks are stuck: `curl -s http://localhost:8000/health | jq '.queue_depth'`
2. Restart the worker with the new image: `docker compose -f docker-compose.prod.yml up -d worker`

Tasks that were enqueued but not yet started will be picked up by the new worker after it starts. The procrastinate task queue is durable (backed by PostgreSQL), so no tasks are lost during the restart.

### 4.5 Multi-Replica Deployments

If you run multiple API or worker replicas (e.g., behind a load balancer):

1. Run migrations once (not per replica).
2. Restart replicas one at a time, waiting for each to pass its health check before restarting the next.
3. The load balancer routes traffic away from the restarting replica automatically.

```bash
# Example: rolling restart of 3 API replicas
docker compose -f docker-compose.prod.yml up -d --no-deps --scale api=3 api
```

---

## 5. Version Compatibility Matrix

This table tracks database migration requirements and breaking changes across releases. Consult it to understand the upgrade path from your current version to the target version.

| Version | Min Alembic Revision | Breaking Changes | Maintenance Window Required | Notes |
|---------|---------------------|------------------|-----------------------------|-------|
| v1.0.0  | `0003`              | --               | No (initial release)        | Initial release. 3 migrations: `0001` (15 core tables), `0002` (workflow_code_versions), `0003` (alert dedup columns + fingerprint index). |

### How to Read This Table

- **Min Alembic Revision:** The minimum database migration revision required for this application version to function. If your database is below this revision, `alembic upgrade head` will apply the necessary migrations.
- **Breaking Changes:** API changes that require client updates -- renamed endpoints, removed fields, changed authentication behavior.
- **Maintenance Window Required:** Whether the migrations in this release are backward-compatible with the previous version's code. `No` means the migration-first zero-downtime approach is safe. `Yes` means services must be stopped before migrating.

### Upgrade Path Examples

**v1.0.0 (fresh install):**

```bash
docker run --rm --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.0.0 \
  alembic upgrade head
```

This applies all three migrations (`0001` through `0003`) in sequence.

**Future: v1.0.0 to v1.1.0:**

```bash
# Alembic applies only the delta — migrations 0004+ if they exist
docker run --rm --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head
```

You never need to apply migrations one version at a time. Alembic walks the full migration chain from your current revision to `head`, regardless of how many versions you skip.

---

## 6. Post-Upgrade Smoke Test Checklist

Run these checks after every upgrade to verify all subsystems are operational. All commands use the production compose file. Adjust the file path and API key as needed.

### 6.1 Health Endpoint Returns 200

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
# Expected: 200

curl -s http://localhost:8000/health | jq .
# Expected: status=ok, db=ok, queue_depth near 0
```

### 6.2 API Key Authentication Works

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/v1/alerts \
  -H "Authorization: Bearer $CALSETA_KEY"
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/v1/alerts \
  -H "Authorization: Bearer cai_invalid_key_here"
# Expected: 401
```

### 6.3 Ingest a Test Alert

Send a test alert through the generic ingest endpoint:

```bash
curl -s -X POST http://localhost:8000/v1/alerts \
  -H "Authorization: Bearer $CALSETA_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "generic",
    "payload": {
      "title": "Upgrade smoke test alert",
      "severity": "Low",
      "description": "Verifying alert ingestion after upgrade"
    }
  }'
# Expected: HTTP 202 with alert_uuid in response
```

### 6.4 Verify Enrichment Runs

After ingesting a test alert with indicators, check that the worker processes enrichment tasks:

```bash
# Check worker logs for enrichment activity
docker compose -f docker-compose.prod.yml logs --tail=20 worker | grep -i "enrich"

# Check queue depth is decreasing (not stuck)
curl -s http://localhost:8000/health | jq '.queue_depth'
# Expected: 0 or decreasing toward 0

# Check enrichment provider status
curl -s http://localhost:8000/health | jq '.enrichment_providers'
# Expected: providers you configured show "configured"
```

### 6.5 Verify MCP Server Responds

```bash
# Check MCP server is reachable (basic TCP check)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/
# Expected: a response (status code varies by MCP protocol version)

# Check MCP container is running
docker compose -f docker-compose.prod.yml ps mcp
# Expected: running, healthy
```

### 6.6 Check Metrics Endpoint

```bash
curl -s http://localhost:8000/v1/metrics/summary \
  -H "Authorization: Bearer $CALSETA_KEY" | jq .
# Expected: HTTP 200 with metrics data
```

### 6.7 Verify All Services Are Running

```bash
docker compose -f docker-compose.prod.yml ps
# Expected: api, worker, mcp all show "running" (and db if self-hosted)
```

### 6.8 Check Logs for Errors

```bash
# Check API logs for startup errors
docker compose -f docker-compose.prod.yml logs --tail=50 api | grep -i "error\|critical\|failed"

# Check worker logs
docker compose -f docker-compose.prod.yml logs --tail=50 worker | grep -i "error\|critical\|failed"

# Check MCP logs
docker compose -f docker-compose.prod.yml logs --tail=50 mcp | grep -i "error\|critical\|failed"
```

No `critical` or `startup_*_failed` log lines should appear. Occasional `error` lines from external enrichment providers (rate limits, timeouts) are normal.

---

## Quick Reference

| Task | Command |
|---|---|
| Check current version | `curl -s http://localhost:8000/health` |
| Check migration revision | `docker compose -f docker-compose.prod.yml run --rm api alembic current` |
| Back up database (custom format) | `pg_dump -h HOST -U calseta -d calseta -Fc > backup.dump` |
| Back up database (Docker) | `docker compose exec db pg_dump -U calseta -d calseta -Fc > backup.dump` |
| Pull new image | `docker pull ghcr.io/your-org/calseta-api:v1.1.0` |
| Run migrations | `docker run --rm --env-file .env.prod ghcr.io/your-org/calseta-api:v1.1.0 alembic upgrade head` |
| Restart services | `docker compose -f docker-compose.prod.yml up -d` |
| Stop worker gracefully | `docker compose -f docker-compose.prod.yml stop -t 60 worker` |
| Rollback migration one step | `docker run --rm --env-file .env.prod ghcr.io/your-org/calseta-api:v1.1.0 alembic downgrade -1` |
| Restore database backup | `pg_restore -h HOST -U calseta -d calseta --clean --if-exists backup.dump` |
| Health check | `curl -s http://localhost:8000/health \| jq .` |

---

## Related Documentation

- [HOW_TO_DEPLOY.md](HOW_TO_DEPLOY.md) -- Full deployment guide, including initial setup and production hardening
- [HOW_TO_RUN_MIGRATIONS.md](HOW_TO_RUN_MIGRATIONS.md) -- Detailed migration operations: checking status, rollback, creating new migrations
- [DEVELOPMENT.md](DEVELOPMENT.md) -- Local development workflow
