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
