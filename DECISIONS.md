# Calseta AI — Autonomous Decision Log

Decisions made during autonomous execution. Reviewed by Jorge on return.

Format: `[CHUNK] [DATE] Decision — Rationale`

---

## Chunk 1.1 — Project Scaffold & Docker Compose

**[1.1] [2026-02-28] Build backend: setuptools over hatchling/flit**
Rationale: setuptools is the most universally supported Python build backend, has the widest
compatibility with CI systems and deployment tooling, and is already familiar to most Python
engineers. No compelling reason to use a newer backend for this project type.

**[1.1] [2026-02-28] procrastinate[asyncpg] over procrastinate[sqlalchemy]**
Rationale: The asyncpg connector is simpler to set up and the worker process (separate from the
API) doesn't use SQLAlchemy at all. Using the asyncpg connector directly avoids coupling the
task queue to the ORM layer. The SQLAlchemy integration can be added later if transactional
enqueue-within-request becomes a priority.

**[1.1] [2026-02-28] mypy with explicit strict flags over `strict = true`**
Rationale: `strict = true` enables flags that cause false positives with FastAPI's decorator
patterns and SQLAlchemy's expression language. Using explicit flags (disallow_untyped_defs,
warn_return_any, etc.) achieves strong type safety without fighting framework internals.
Added `ignore_missing_imports = true` since several deps (mcp, procrastinate) have incomplete stubs.

**[1.1] [2026-02-28] docker-compose environment block overrides DATABASE_URL for service-to-service networking**
Rationale: The .env.example uses `localhost:5432` for developers running the app locally
(Python process on host, Postgres in Docker). When running fully in docker compose, services
reference each other by name (`db:5432`). The `environment:` block in docker-compose.yml
overrides the .env value with the docker-internal hostname. Both modes work without touching .env.

---

## Chunk 1.2 — Database Schema & Alembic Migrations

**[1.2] [2026-02-28] indicator_field_mapping ORM model created in 1.2, not 1.7**
Rationale: The initial migration (0001_initial_schema.py) creates all 15 tables including
indicator_field_mappings. Alembic autogenerate needs the ORM model to detect the table in metadata.
Creating the model file in chunk 1.2 ensures the migration works correctly. Chunk 1.7 still owns
the seeder, schemas, and acceptance test — the model file is just moved earlier.

**[1.2] [2026-02-28] alert_indicators join table has no uuid column**
Rationale: Join tables are never referenced externally by UUID — they are queried via their FKs.
Adding a UUID to a join table would be unnecessary overhead and would confuse the "external IDs
are always UUIDs" convention (which applies to first-class entities, not join tables).

---

## Chunk 1.3 — Core Pydantic Schemas

**[1.3] [2026-02-28] PRD has 14 system indicator field mappings, not 17 as stated in PROJECT_PLAN.md**
Rationale: Section 7.12 of the PRD lists exactly 14 CalsetaAlert field → indicator type mappings.
The project plan says "17 system mappings" — this appears to be a planning error. Implemented 14
per the authoritative PRD content. The seeder in chunk 1.7 will insert these 14 rows.

---
