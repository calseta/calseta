# Calseta AI -- Migration Operations Guide

Complete guide for running, inspecting, and troubleshooting Alembic database migrations in Calseta AI.

---

## Table of Contents

1. [What Alembic Is and Why Calseta Uses It](#1-what-alembic-is-and-why-calseta-uses-it)
2. [Checking Current Version](#2-checking-current-version)
3. [Running Migrations to Latest](#3-running-migrations-to-latest)
4. [Rollback on Failure](#4-rollback-on-failure)
5. [Viewing Migration History](#5-viewing-migration-history)
6. [Post-Migration Seeding Behavior](#6-post-migration-seeding-behavior)
7. [Automatic vs. Manual Migration Execution](#7-automatic-vs-manual-migration-execution)
8. [Creating New Migrations (For Contributors)](#8-creating-new-migrations-for-contributors)

---

## 1. What Alembic Is and Why Calseta Uses It

[Alembic](https://alembic.sqlalchemy.org/) is the database migration tool for SQLAlchemy. It tracks schema changes as versioned Python scripts, each containing an `upgrade()` function to apply the change and a `downgrade()` function to reverse it. Alembic records which migration has been applied in an `alembic_version` table inside the database itself, so every database instance knows exactly which schema version it is running.

Calseta uses Alembic because the platform is self-hosted. Operators deploy their own PostgreSQL instance and update Calseta at their own pace. Migrations guarantee that the database schema matches the application code at every version -- whether the operator is upgrading from v1.0.0 to v1.1.0 or deploying fresh. Without migrations, schema drift would cause silent data corruption or hard-to-diagnose runtime errors.

Calseta's Alembic environment is configured for async SQLAlchemy 2.0 with the `asyncpg` driver (`alembic/env.py`). The database URL is read from the `DATABASE_URL` environment variable via `app/config.py`, so the same `.env` file or environment that runs the application also drives migrations.

---

## 2. Checking Current Version

To see which migration revision the database is currently at:

**Inside Docker (recommended):**

```bash
docker compose run --rm api alembic current
```

**Bare Alembic (if Python environment is set up locally):**

```bash
alembic current
```

### Interpreting the Output

A healthy database shows the current revision ID and `(head)` if it is up to date:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0003 (head)
```

- `0003` -- the database is at revision `0003`.
- `(head)` -- this is the latest migration in the codebase. No pending migrations.

If the output shows a revision **without** `(head)`, there are pending migrations that need to be applied:

```
0001
```

This means the database is at revision `0001` and there are newer migrations (`0002`, `0003`, ...) waiting to run.

If the output is empty (no revision displayed), the database has no `alembic_version` table and has never been migrated -- either it is a fresh database or was set up outside of Alembic.

### Where Version Tracking Is Stored

Alembic creates a single-row table called `alembic_version` in the public schema. It has one column, `version_num`, which holds the current revision ID string. You can inspect it directly:

```sql
SELECT version_num FROM alembic_version;
```

Never modify this table manually unless you fully understand the implications. Alembic uses it as the source of truth for determining which migrations to run.

---

## 3. Running Migrations to Latest

To apply all pending migrations and bring the database schema up to date:

**Inside Docker (recommended):**

```bash
docker compose run --rm api alembic upgrade head
```

**Production (using a pre-built image):**

```bash
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head
```

**Bare Alembic (local development with Python environment):**

```bash
alembic upgrade head
```

**Make target (local development, requires running database):**

```bash
make migrate
```

### What Happens During Migration

1. Alembic connects to the database using the `DATABASE_URL` from your environment or `.env` file.
2. It reads the current `alembic_version` table to determine the starting revision.
3. It executes each pending migration's `upgrade()` function in order, inside a transaction.
4. After each migration completes, it updates `alembic_version` to the new revision.
5. If any migration fails, the transaction is rolled back and `alembic_version` remains unchanged.

### Expected Output

A successful migration run looks like this:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, add workflow_code_versions
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, add alert dedup columns and fingerprint index
```

If the database is already at `head`, you will see:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

No "Running upgrade" lines appear because there is nothing to do.

---

## 4. Rollback on Failure

### Roll Back One Step

To undo the most recently applied migration:

```bash
# Docker
docker compose run --rm api alembic downgrade -1

# Bare
alembic downgrade -1
```

### Roll Back to a Specific Revision

To downgrade to a known-good revision:

```bash
# Docker
docker compose run --rm api alembic downgrade 0001

# Bare
alembic downgrade 0001
```

This runs the `downgrade()` function of every migration between the current version and the target, in reverse order.

### Roll Back to Zero (Empty Database)

To undo all migrations and drop all Calseta tables:

```bash
docker compose run --rm api alembic downgrade base
```

This is destructive -- all data is lost. Only use this on development databases.

### When Rollback Is Safe

Rollback is safe when the migration only performed **additive DDL changes** -- creating tables, adding columns with defaults, creating indexes. All three of Calseta's current migrations (`0001`, `0002`, `0003`) fall into this category and have fully reversible `downgrade()` functions.

### When Rollback Needs Manual Intervention

Rollback may need manual intervention when:

- **Data has been written to new columns or tables** and the downgrade drops them. The data in those columns is lost permanently. If you need to preserve it, export the data before downgrading.
- **A migration changed column types or constraints** and the original type cannot hold the current data (e.g., a column was widened from `VARCHAR(100)` to `TEXT`, then data longer than 100 characters was inserted).
- **The migration included irreversible operations** like `DROP TABLE` or data transformations. Well-written migrations always have a `downgrade()` path, but check the migration file before assuming.
- **The database was modified outside of Alembic** (manual `ALTER TABLE` statements, pg_dump/restore from a different version). In this case, `alembic_version` no longer reflects the actual schema, and downgrade may fail with column-not-found or table-already-exists errors.

**Before rolling back in production:** Always take a database backup first. Verify the specific migration's `downgrade()` function by reading the migration file in `alembic/versions/`.

---

## 5. Viewing Migration History

### Full History

To see all migrations in the chain:

```bash
# Docker
docker compose run --rm api alembic history --verbose

# Bare
alembic history --verbose
```

Example output:

```
Rev: 0003 (head)
Parent: 0002
Path: alembic/versions/0003_add_alert_dedup_columns.py

    add alert deduplication columns and fingerprint index

    Revision ID: 0003
    Revises: 0002
    Create Date: 2026-03-01

Rev: 0002
Parent: 0001
Path: alembic/versions/0002_add_workflow_code_versions.py

    add workflow_code_versions table

    Revision ID: 0002
    Revises: 0001
    Create Date: 2026-02-28

Rev: 0001
Parent: <base>
Path: alembic/versions/0001_initial_schema.py

    Initial schema — all 15 core tables.

    Revision ID: 0001
    Revises:
    Create Date: 2026-02-28
```

### Show Details of a Specific Revision

```bash
# Docker
docker compose run --rm api alembic show 0002

# Bare
alembic show 0002
```

This displays the full docstring, revision ID, parent revision, and file path for that migration.

### Compact History

For a shorter view:

```bash
docker compose run --rm api alembic history
```

Output:

```
0001 -> 0002 (head), add workflow_code_versions table
<base> -> 0001, initial schema
```

---

## 6. Post-Migration Seeding Behavior

After migrations create the database schema, Calseta automatically seeds essential system data on **API server startup** (not during the migration itself). This happens in the `lifespan` event handler in `app/main.py`.

### What Gets Seeded

Three seeders run in sequence every time the API server starts:

1. **System indicator field mappings** (`app/seed/indicator_mappings.py`) -- Inserts 14 standard CalsetaAlert-to-indicator-type mappings (e.g., `src_ip` -> `ip`, `file_hash_sha256` -> `hash_sha256`). These power the indicator extraction pipeline's Pass 2 (normalized-field mappings).

2. **Built-in workflows** (`app/seed/builtin_workflows.py`) -- Upserts 9 pre-built system workflows: 5 Okta workflows (revoke sessions, suspend user, unsuspend user, reset password, force password expiry) and 4 Entra workflows (revoke sessions, disable account, enable account, force MFA re-registration). Activation state is determined by whether the corresponding integration credentials (`OKTA_DOMAIN`/`OKTA_API_TOKEN` or `ENTRA_TENANT_ID`/`ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET`) are configured.

3. **Normalized mapping cache** (`app/services/indicator_mapping_cache.py`) -- Loads active normalized-target indicator field mappings into an in-memory cache used for fingerprint extraction at ingest time.

### Seeder Idempotency

All seeders are idempotent and safe to run on every server restart:

- **Indicator field mappings**: Checked by `(field_path, extraction_target)` pair. If a mapping already exists, it is skipped -- not updated. Manual changes to existing rows (e.g., toggling `is_active`) are preserved across restarts.
- **Built-in workflows**: Matched by `name` + `is_system=True`. Existing system workflows are not overwritten. The upsert only inserts if no matching row exists.
- **Mapping cache**: Reloaded from the database on every startup. No destructive operations.

### Failure Behavior

If seeding fails (for example, because migrations have not been run and the tables do not exist), the API server logs a `startup_seed_failed` warning and **continues to start**. The platform operates in a degraded mode:

- Alert ingestion still works, but indicator extraction from normalized fields may be incomplete.
- Built-in workflows are not available in the workflow catalog.

The fix is to run `alembic upgrade head` and restart the API server.

---

## 7. Automatic vs. Manual Migration Execution

### Development: Automatic Migration via `make dev`

In local development, the `make dev` target handles migrations automatically:

```bash
make dev
```

This runs the following sequence:

1. Starts PostgreSQL (`docker compose up -d db`)
2. Waits for the database to be ready (`pg_isready`)
3. Runs `docker compose run --rm api alembic upgrade head`
4. Applies the procrastinate task queue schema
5. Starts all services (`docker compose up`)

For faster restarts when no new migrations exist, use:

```bash
make dev-up
```

This skips the migration step and directly starts all services.

### Production: Manual Migration as a Pre-Deployment Step

In production, **always run migrations manually before starting the new application version**. The migration command must use the **new** image (which contains the new migration files) against the **existing** database:

```bash
# Step 1: Run migrations with the new image
docker run --rm \
  --env-file .env.prod \
  ghcr.io/your-org/calseta-api:v1.1.0 \
  alembic upgrade head

# Step 2: Update image tags and restart services
docker compose -f docker-compose.prod.yml up -d
```

### Why Production Should Not Auto-Migrate

Auto-migration on startup is convenient for development but dangerous in production for several reasons:

- **Race conditions**: If multiple API replicas start simultaneously, they may all attempt to run migrations concurrently. While PostgreSQL's transactional DDL provides some protection, concurrent migrations can lead to deadlocks or duplicate operations depending on the specific DDL statements.
- **Rollback difficulty**: If a migration succeeds but the application has a bug, the database is already at the new schema. Rolling back the application version without also rolling back the migration can cause runtime errors from schema mismatches.
- **Observability**: Running migrations as a separate step produces a clear, isolated log output. You know exactly whether the migration succeeded or failed before any application traffic is served.
- **Timeout risk**: Long-running migrations (adding indexes to large tables, backfilling data) can exceed container startup timeouts, causing orchestrators (ECS, Kubernetes) to kill the container and restart it in a loop.
- **Controlled blast radius**: A failed migration in a separate step stops the deployment pipeline. A failed migration embedded in startup may crash one replica while others continue serving traffic with an inconsistent schema.

For the full production deployment workflow, see [HOW_TO_DEPLOY.md](HOW_TO_DEPLOY.md), Section 4 (Production Deployment) and Section 7 (Updating to a New Version).

---

## 8. Creating New Migrations (For Contributors)

### Step 1: Generate a Migration

After modifying SQLAlchemy models in `app/db/models/`, generate a migration:

```bash
# Docker (recommended — ensures the same Python environment as CI)
docker compose run --rm api alembic revision --autogenerate -m "add foobar column to alerts"

# Bare
alembic revision --autogenerate -m "add foobar column to alerts"
```

Alembic compares the current database schema against the SQLAlchemy model metadata and generates a migration file in `alembic/versions/` with the detected differences.

### Step 2: Review the Generated Migration

**Never blindly trust autogenerate.** Open the generated file and verify:

- The `upgrade()` function contains exactly the changes you intended.
- The `downgrade()` function correctly reverses every operation in `upgrade()`.
- No unrelated changes were picked up (e.g., from uncommitted model changes by another contributor).
- PostgreSQL-specific types (`postgresql.JSONB`, `postgresql.ARRAY`, `postgresql.UUID`) are imported correctly.
- Table and column names match the project conventions (snake_case, descriptive).

Autogenerate limitations -- it cannot detect:
- Table or column renames (it sees a drop + create instead).
- Changes to `server_default` values.
- Changes to `CHECK` constraints.
- Custom SQL operations (extension creation, stored procedures, data migrations).

For these, write the `upgrade()` and `downgrade()` operations manually using `op.execute()`.

### Step 3: Test Upgrade AND Downgrade

```bash
# Apply the new migration
docker compose run --rm api alembic upgrade head

# Verify the new migration is current
docker compose run --rm api alembic current

# Test the downgrade path
docker compose run --rm api alembic downgrade -1

# Verify you are back at the previous revision
docker compose run --rm api alembic current

# Re-apply to leave the database in the correct state
docker compose run --rm api alembic upgrade head
```

### Step 4: Run the Application and Tests

```bash
# Start services to confirm the API starts with the new schema
make dev

# Run the test suite
make test
```

### Migration File Naming Convention

Calseta uses numeric prefixes for migration revision IDs (`0001`, `0002`, `0003`, ...) and descriptive filenames. The autogenerate command uses Alembic's default random hex revision IDs. After generation, consider renaming the file and updating the `revision` variable to follow the numeric pattern:

```
alembic/versions/0004_add_foobar_column_to_alerts.py
```

Inside the file:

```python
revision = "0004"
down_revision = "0003"
```

### Commit Message Convention

```
feat: add foobar column to alerts table

Adds alembic migration 0004 for the new foobar column on alerts.
```

### Checklist Before Merging

- [ ] Migration file has both `upgrade()` and `downgrade()` functions
- [ ] `downgrade()` fully reverses `upgrade()`
- [ ] `alembic upgrade head` succeeds on a fresh database
- [ ] `alembic downgrade -1` followed by `alembic upgrade head` succeeds
- [ ] `make test` passes
- [ ] `make lint` and `make typecheck` pass
- [ ] No unintended schema changes in the migration

---

## Quick Reference

| Task | Docker Command | Bare Command |
|---|---|---|
| Check current version | `docker compose run --rm api alembic current` | `alembic current` |
| Apply all pending | `docker compose run --rm api alembic upgrade head` | `alembic upgrade head` |
| Apply next one only | `docker compose run --rm api alembic upgrade +1` | `alembic upgrade +1` |
| Roll back one step | `docker compose run --rm api alembic downgrade -1` | `alembic downgrade -1` |
| Roll back to revision | `docker compose run --rm api alembic downgrade 0001` | `alembic downgrade 0001` |
| Roll back to zero | `docker compose run --rm api alembic downgrade base` | `alembic downgrade base` |
| View full history | `docker compose run --rm api alembic history --verbose` | `alembic history --verbose` |
| Show single revision | `docker compose run --rm api alembic show 0002` | `alembic show 0002` |
| Generate new migration | `docker compose run --rm api alembic revision --autogenerate -m "desc"` | `alembic revision --autogenerate -m "desc"` |
| Run migrations (make) | -- | `make migrate` |
