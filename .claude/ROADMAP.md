# Claude Tooling Roadmap

Ideas for improving the Claude Code setup in this repo. Not product features — dev tooling only.

---

## Post-MVP: Direct Log Destination Adapters

For deployments that cannot route stdout (uncommon), add optional `LOG_DESTINATION` adapters:

- `stdout` — default, already shipped
- `cloudwatch` — via `watchtower` library; requires `AWS_LOG_GROUP` + IAM role
- `azure_monitor` — via `opencensus-ext-azure`; requires `APPLICATIONINSIGHTS_CONNECTION_STRING`

**Design:** Each adapter lives in `app/logging/handlers/{destination}.py`. `configure_logging()` in `app/logging_config.py` checks `LOG_DESTINATION` at startup and registers the appropriate handler. No application code outside `logging_config.py` is aware of the destination. Core libraries are never imported unless that destination is active.

---

## API Key Source Restriction

Lock an API key to specific ingest sources so a Sentinel webhook key cannot POST to `/v1/ingest/elastic`.

**Design notes (when ready to build):**
- `api_keys` table already has `allowed_sources TEXT[]` stubbed as `NULL` (= unrestricted) per PRD Section 11 — no migration needed
- Auth middleware checks: if `api_key.allowed_sources` is not null and the ingest source is not in the list, reject with `403 FORBIDDEN`
- Enforced only on `POST /v1/ingest/{source_name}` — all other endpoints unaffected
- Surface in `POST /v1/api-keys` request body as optional `allowed_sources: list[str]`

---

## Post-MVP: Switch to Gitflow branching

Once MVP ships, migrate from the single `feat/mvp-dev` branch to a proper Gitflow strategy:

```
main        ← stable tagged releases
develop     ← integration branch
└── feat/wave-N-*    per-wave or per-chunk feature branches
└── fix/*            bug fix branches
└── hotfix/*         urgent fixes from main
```

Steps:
1. Merge `feat/mvp-dev` → `main`, tag `v1.0.0`
2. Create `develop` from `main`
3. Update `CLAUDE.md` branching section to reflect new strategy
4. Update `CONTRIBUTING.md` with full external contributor workflow (fork → branch → PR into `develop`)
5. Update CI to require PRs into `develop` (not `main`)

---

## `/wave <wave-number>` — Parallel wave execution

Execute all chunks in a PROJECT_PLAN.md wave using parallel subagents, respecting the dependency graph and ⚡ parallelism markers.

**Design notes (when ready to build):**
- Each subagent runs the `/chunk` logic independently
- Agents write completion logs to `.claude/chunk-logs/{chunk-id}.md` instead of directly to `PROJECT_PLAN.md` to avoid write conflicts
- A companion `/wave-merge` command collects those files and writes them into `PROJECT_PLAN.md` cleanly
- Command validates all wave dependencies are `complete` before spawning anything
- Works best on waves with many independent chunks (e.g., Wave 3 — enrichment providers)
- Wave 1 has internal sequencing so only 2–3 chunks can actually parallelize — less benefit there
