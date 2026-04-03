# Upgrade Experience

**Date**: 2026-03-27
**Author**: Jorge Castro
**Status**: Draft

## Problem Statement

Calseta is a self-hosted Docker Compose application. Today, upgrading to a new version requires users to manually pull new images, run Alembic migrations, and restart services — in the right order, with no safety net. There's no CHANGELOG, no schema version visibility, no backup-before-migrate, and no single command to upgrade. For a project designed around "deploy in under an hour," the ongoing upgrade story is fragile and undocumented.

This matters especially as v1.1.0 (architecture deepening) and v2.0 (agent control plane) ship with schema migrations and potentially breaking changes. Self-hosters who forget `alembic upgrade head` will get cryptic SQLAlchemy errors. Teams running multiple instances risk partial migrations.

## Solution

Ship a zero-friction upgrade path where `docker compose pull && docker compose up -d` just works — migrations run automatically, schema version is visible in health checks, and every release has a clear CHANGELOG entry documenting what changed, what migrated, and what broke. Major version upgrades (1.x → 2.0) get a dedicated migration guide.

After this ships, a user upgrading Calseta should:
1. Read the CHANGELOG for their target version
2. Run `make upgrade` (or just `docker compose pull && docker compose up -d`)
3. Verify via `/health` that schema and app version match expectations

## User Stories

1. As a self-hoster, I want migrations to run automatically on container startup so I never get cryptic errors from a stale schema.
2. As a self-hoster, I want only one container instance to run migrations at a time so parallel startups don't race on schema changes.
3. As a self-hoster, I want the `/health` endpoint to include the current Alembic schema revision so I can verify my database is up to date.
4. As a self-hoster, I want a `make upgrade` command that backs up my database, pulls new images, and restarts services in one step.
5. As a self-hoster, I want a `make backup-db` command I can run independently before any risky operation.
6. As a self-hoster, I want a CHANGELOG.md that tells me what changed in each release — new features, breaking changes, new env vars, and migration notes.
7. As a self-hoster upgrading across major versions (1.x → 2.0), I want a dedicated migration guide that walks me through breaking changes and data transforms.
8. As a self-hoster, I want the worker and MCP containers to wait for migrations to complete before starting, so they never run against a stale schema.
9. As a self-hoster, I want to see a clear log line at startup indicating whether migrations were applied or already current.
10. As a developer contributing to Calseta, I want a release checklist template so every release includes CHANGELOG updates and migration notes.
11. As a self-hoster running in production, I want the migration entrypoint to fail fast and loudly if a migration errors, rather than starting the app on a broken schema.
12. As a self-hoster, I want `make upgrade` to verify the health endpoint returns 200 after restart, confirming the upgrade succeeded.

## Implementation Decisions

### Auto-migration entrypoint script

A `docker-entrypoint.sh` bash script replaces direct `CMD` invocations in Docker Compose. The script:
- Checks `RUN_MIGRATIONS` env var (set only on the `api` service)
- If true: acquires a PostgreSQL advisory lock, runs `alembic upgrade head`, logs result, releases lock
- If migration fails: exits non-zero immediately (container crashes, Compose restarts or alerts)
- Then `exec`s the original command (`uvicorn`, `python -m app.worker`, etc.)

Advisory lock prevents races when multiple api replicas start simultaneously (relevant for cloud deployments with replicas > 1). The lock is per-database, not per-table — cheap and sufficient.

Worker and MCP services use `depends_on: api: condition: service_healthy` to wait for the api container (and its migrations) to be healthy before starting. This already partially exists in the Compose file.

### Schema version in health endpoint

The existing `/health` endpoint (`app/api/health.py`) already returns `version` (app version). Add `schema_revision` — the current Alembic head revision from the database. This is a single query: `SELECT version_num FROM alembic_version`. If the revision doesn't match the app's expected head, health can flag it.

Also add `schema_up_to_date: bool` — compares DB revision against the app's bundled Alembic head. This gives monitoring systems a simple boolean to alert on.

### Makefile upgrade target

`make upgrade` orchestrates the full upgrade:
1. `make backup-db` (pg_dump to timestamped file)
2. `docker compose pull`
3. `docker compose up -d` (triggers entrypoint, which runs migrations)
4. Wait for health check to return 200
5. Print summary: old version → new version, migrations applied, backup location

`make backup-db` is a standalone target: `docker compose exec db pg_dump -U postgres calseta > backups/calseta_$(date +%Y%m%d_%H%M%S).sql`

### CHANGELOG.md

Follow Keep a Changelog format (https://keepachangelog.com). Sections per release: Added, Changed, Deprecated, Removed, Fixed, Security, Migration Notes. The Migration Notes section is Calseta-specific — lists new env vars, schema changes, and any manual steps.

Retroactively write entries for v1.0.0. Going forward, every PR that touches the API, schema, config, or behavior updates the `[Unreleased]` section.

### Major version migration guides

For v2.0 (agent control plane), ship `docs/guides/UPGRADING.md` with:
- Version-specific sections (e.g., "Upgrading from 1.x to 2.0")
- Breaking changes with before/after examples
- Data migration details (what Alembic handles vs. manual steps)
- Rollback instructions

This file is referenced from CHANGELOG.md entries for major versions.

### Release checklist

A `.github/RELEASE_CHECKLIST.md` template (or PR template addition) ensuring every release:
- Updates CHANGELOG.md
- Adds migration notes if schema changed
- Updates UPGRADING.md if breaking changes
- Tags with semver
- Tests upgrade path from previous version

## Testing Strategy

- **Entrypoint script**: Integration test that starts two containers simultaneously and verifies only one runs migrations (check advisory lock behavior). Also test failure mode: bad migration → container exits non-zero.
- **Health endpoint schema version**: Unit test that `/health` returns `schema_revision` and `schema_up_to_date` fields. Integration test against real DB verifying the revision matches.
- **Makefile targets**: Manual verification (these are orchestration commands, not application logic). Document the test procedure in the PR.
- **Upgrade path**: End-to-end test in CI that starts v1.0.0, seeds data, upgrades to current, and verifies data integrity + health. This is the most valuable test but also the most complex — can be a follow-up.

## Out of Scope

- **Automatic rollback on failed migration**: Alembic downgrade is available but auto-rollback adds significant complexity. Users can manually `alembic downgrade` if needed. Revisit if upgrade failures become common.
- **Blue-green deployment support**: Cloud-native deployment PRD covers this. This PRD focuses on the single-instance Docker Compose experience.
- **UI upgrade wizard**: No frontend work. Upgrades are CLI/Docker operations.
- **Automatic CHANGELOG generation from commits**: Conventional commits tooling (e.g., `git-cliff`) is nice but not necessary for a project this size. Manual CHANGELOG is more accurate.
- **Database migration testing framework**: A framework for testing migrations against production-like data. Valuable but separate effort.

## Open Questions

1. **Backup retention policy**: Should `make backup-db` auto-prune old backups? Or leave that to the user? Leaning toward user responsibility with a note in docs.
2. **Migration lock timeout**: How long should the advisory lock wait before giving up? 30 seconds seems reasonable. If another instance is mid-migration for longer than that, something is wrong.
3. **Health endpoint auth**: `/health` is currently unauthenticated. Adding `schema_revision` (an Alembic hash) is low-risk, but `schema_up_to_date: false` could signal vulnerability to attackers. Consider a separate `/health/detailed` behind auth. Leaning toward keeping it simple — the revision hash reveals nothing actionable.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Advisory lock doesn't release on crash | Low | Medium | PostgreSQL auto-releases advisory locks on session disconnect. Use session-level lock, not transaction-level. |
| Migration runs on every restart, adding startup latency | Certain | Low | `alembic upgrade head` is a no-op when already current (~50ms). Acceptable. |
| Users skip `make upgrade` and just `docker compose up` | High | Low | Entrypoint handles migrations regardless. `make upgrade` just adds backup + verification. |
| Backup fills disk on small VMs | Medium | Medium | Document backup location and retention. Don't auto-backup on every restart — only on explicit `make upgrade`. |

## Project Management

### Overview

| Chunk | Wave | Status | Dependencies |
|-------|------|--------|-------------|
| Entrypoint script + Dockerfile | 1 | pending | — |
| Health endpoint schema version | 1 | pending | — |
| CHANGELOG.md (retroactive + template) | 1 | pending | — |
| Makefile upgrade + backup targets | 2 | pending | Entrypoint script |
| Docker Compose wiring | 2 | pending | Entrypoint script |
| UPGRADING.md template + release checklist | 2 | pending | CHANGELOG.md |
| Integration test: upgrade path | 3 | pending | All Wave 1 + 2 |

### Wave 1 — Foundation

All chunks in Wave 1 are independent — no shared files.

#### Chunk: Entrypoint script + Dockerfile

- **What**: Create `docker-entrypoint.sh` with advisory-lock-guarded migration execution. Update Dockerfile to `COPY` and `ENTRYPOINT` the script. Script checks `RUN_MIGRATIONS` env var, acquires `pg_advisory_lock(hashtext('calseta_migrations'))`, runs `alembic upgrade head`, logs result, execs original CMD.
- **Why this wave**: Foundational — everything else depends on migrations running automatically.
- **Modules touched**: `docker-entrypoint.sh` (new), `Dockerfile`
- **Depends on**: None
- **Produces**: Entrypoint that auto-migrates; other chunks reference this behavior
- **Acceptance criteria**:
  - [ ] `docker-entrypoint.sh` exists and is executable
  - [ ] Dockerfile COPY and ENTRYPOINT reference the script
  - [ ] With `RUN_MIGRATIONS=true`, container runs `alembic upgrade head` before starting app
  - [ ] Without `RUN_MIGRATIONS`, container starts app directly (no migration attempt)
  - [ ] Failed migration exits non-zero with clear error log
  - [ ] Advisory lock acquired/released around migration (verified via log output)
- **Verification**: Build image, start with `RUN_MIGRATIONS=true`, check logs show migration output. Start without env var, verify no migration log.

#### Chunk: Health endpoint schema version

- **What**: Add `schema_revision` (string) and `schema_up_to_date` (bool) to `/health` response. Query `alembic_version` table for current revision. Compare against app's bundled head (read from Alembic config at startup, cached).
- **Why this wave**: Independent of entrypoint — reads DB state, doesn't write it.
- **Modules touched**: `app/api/health.py`, `app/config.py` (add `ALEMBIC_HEAD_REVISION` computed at startup)
- **Depends on**: None
- **Produces**: Health endpoint contract that monitoring/upgrade scripts can check
- **Acceptance criteria**:
  - [ ] `/health` response includes `schema_revision` field (string, current Alembic revision)
  - [ ] `/health` response includes `schema_up_to_date` field (bool)
  - [ ] When DB is at head, `schema_up_to_date` is `true`
  - [ ] When DB is behind, `schema_up_to_date` is `false`
  - [ ] Query failure returns `schema_revision: "unknown"` and `schema_up_to_date: false`
- **Verification**: `curl localhost:8000/health | jq '.schema_revision, .schema_up_to_date'`

#### Chunk: CHANGELOG.md

- **What**: Create `CHANGELOG.md` at repo root following Keep a Changelog format. Write retroactive entry for v1.0.0 (summarize from git history and PROJECT_PLAN). Add `[Unreleased]` section. Add `[1.1.0]` section stub for architecture deepening work in progress.
- **Why this wave**: Documentation only — no code files touched.
- **Modules touched**: `CHANGELOG.md` (new)
- **Depends on**: None
- **Produces**: Template and convention for all future releases
- **Acceptance criteria**:
  - [ ] `CHANGELOG.md` exists at repo root
  - [ ] Follows Keep a Changelog format with Added/Changed/Fixed/Security/Migration Notes sections
  - [ ] v1.0.0 entry covers key features shipped
  - [ ] `[Unreleased]` section exists for ongoing work
  - [ ] Migration Notes section documents schema changes and new env vars per release
- **Verification**: File exists, renders correctly on GitHub, sections are present.

### Wave 2 — Integration

Depends on Wave 1 entrypoint script and CHANGELOG existing.

#### Chunk: Makefile upgrade + backup targets

- **What**: Add `make backup-db` (pg_dump to `backups/` dir with timestamp) and `make upgrade` (backup → pull → up → health check → summary). Create `backups/` dir with `.gitkeep`. Add `backups/*.sql` to `.gitignore`.
- **Why this wave**: `make upgrade` references the entrypoint behavior (migrations run on `docker compose up`).
- **Modules touched**: `Makefile`, `.gitignore`, `backups/.gitkeep` (new)
- **Depends on**: Entrypoint script (Wave 1)
- **Produces**: User-facing upgrade command
- **Acceptance criteria**:
  - [ ] `make backup-db` creates timestamped SQL dump in `backups/`
  - [ ] `make upgrade` runs backup, pull, up, and health verification in sequence
  - [ ] `make upgrade` prints old/new version and backup location
  - [ ] `make upgrade` fails with clear message if health check doesn't return 200 within 60s
  - [ ] `backups/*.sql` is gitignored
- **Verification**: Run `make backup-db`, verify dump file exists. Run `make upgrade` on already-current version, verify no-op success.

#### Chunk: Docker Compose wiring

- **What**: Update `docker-compose.yml` to use entrypoint script. Set `RUN_MIGRATIONS=true` only on `api` service. Ensure `worker` and `mcp` have `depends_on: api: condition: service_healthy`. Add production compose override (`docker-compose.prod.yml`) that uses tagged images instead of local build.
- **Why this wave**: Depends on entrypoint script existing.
- **Modules touched**: `docker-compose.yml`, `docker-compose.prod.yml` (new)
- **Depends on**: Entrypoint script (Wave 1)
- **Produces**: Working auto-migration on `docker compose up`
- **Acceptance criteria**:
  - [ ] `api` service sets `RUN_MIGRATIONS=true` and uses entrypoint
  - [ ] `worker` and `mcp` depend on `api` being healthy
  - [ ] `docker compose up` from clean state: migrations run, all services start
  - [ ] `docker compose up` from current state: migrations are no-op, services start fast
  - [ ] `docker-compose.prod.yml` uses `ghcr.io` image tags
- **Verification**: `docker compose down -v && docker compose up -d`, check logs show migration, health returns 200.

#### Chunk: UPGRADING.md + release checklist

- **What**: Create `docs/guides/UPGRADING.md` with general upgrade instructions and a v1.0.0 → v1.1.0 section (placeholder for architecture deepening changes). Create `.github/RELEASE_CHECKLIST.md` with the release process steps.
- **Why this wave**: References CHANGELOG format from Wave 1.
- **Modules touched**: `docs/guides/UPGRADING.md` (new), `.github/RELEASE_CHECKLIST.md` (new)
- **Depends on**: CHANGELOG.md (Wave 1)
- **Produces**: Evergreen upgrade guide and release process
- **Acceptance criteria**:
  - [ ] `UPGRADING.md` has general instructions + version-specific section template
  - [ ] `RELEASE_CHECKLIST.md` covers CHANGELOG, migration notes, tag, image push, UPGRADING.md
  - [ ] Both render correctly on GitHub
- **Verification**: Review rendered markdown.

### Wave 3 — Verification

#### Chunk: Integration test — upgrade path

- **What**: CI workflow or script that starts Calseta at a pinned previous version (v1.0.0 image), seeds test data, upgrades to current branch, and verifies: health returns 200, `schema_up_to_date` is true, seeded data is intact and queryable. This catches migration bugs before release.
- **Why this wave**: Needs all infrastructure from Wave 1 + 2 in place.
- **Modules touched**: `tests/integration/test_upgrade_path.py` (new) or `.github/workflows/upgrade-test.yml` (new)
- **Depends on**: All Wave 1 + Wave 2 chunks
- **Produces**: CI safety net for future releases
- **Acceptance criteria**:
  - [ ] Test seeds data on v1.0.0 schema
  - [ ] Test upgrades to current version (runs entrypoint with migrations)
  - [ ] Test verifies health endpoint shows `schema_up_to_date: true`
  - [ ] Test verifies seeded data is still queryable after migration
  - [ ] Test runs in CI (GitHub Actions)
- **Verification**: `pytest tests/integration/test_upgrade_path.py` or CI workflow passes.
