# Part 3: Skills

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 3: Skills](part-3-skills.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 3: Skills

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 6 (delivered alongside KB + Memory)

---

### Problem Statement

A managed agent built on a general-purpose foundation model has no innate knowledge of how Calseta operates. It does not know that findings must be posted via the `post_finding` MCP tool, that severity is an integer enum, that account-compromise alerts have a specific triage flow, or that the `/v1/alerts` endpoint accepts a particular payload shape. Without this operating manual, the agent improvises.

The empirical evidence is direct. Run a `claude_code` adapter against an alert with no operational context attached and the run produces a free-form markdown report — useful prose, but no `post_finding` call, no Calseta-shaped data, no follow-on actions. Attach the bundled `calseta` skill (`app/skills/calseta/SKILL.md`, ~26 KB covering env vars, the REST and MCP surface, the finding format, and the operational rules) and the same agent on the same alert calls `post_finding` with the right payload, follows the documented investigation flow, and respects the platform's conventions.

Skills are how Calseta carries that operating manual into every run. They are a sibling pillar to Knowledge Base and Memory, distinct in purpose:

- **Knowledge Base pages** are *per-investigation* context — runbooks injected because a specific alert matches their targeting rules. Selective, targeted, sometimes large.
- **Memory pages** are *learned* context — entity profiles, codebase maps, and patterns the agent itself wrote during prior runs.
- **Skills** are *persistent reference manuals* — invariant material the agent consults every time it runs, regardless of which alert it is working. Skills are the layer that turns a generic model into a Calseta-shaped operator.

---

### Data Model

Three tables, all created in the agent control plane migration.

#### `skills`

| Column        | Type        | Notes                                                                                     |
| ------------- | ----------- | ----------------------------------------------------------------------------------------- |
| `id`          | bigint      | PK, autoincrement                                                                         |
| `uuid`        | uuid        | External identifier                                                                       |
| `slug`        | text        | NOT NULL, UNIQUE — stable identifier (`calseta`, `account-compromise-ir`)                 |
| `name`        | text        | NOT NULL — human-readable display name                                                    |
| `description` | text        | NULL — short summary surfaced in operator UI                                              |
| `is_active`   | boolean     | NOT NULL, default true — soft-disable without deleting                                    |
| `is_global`   | boolean     | NOT NULL, default false — true means "every managed agent receives this skill"            |
| `created_at`  | timestamptz | NOT NULL                                                                                  |
| `updated_at`  | timestamptz | NOT NULL                                                                                  |

#### `skill_files`

A skill is a directory. Each row is one file inside it.

| Column     | Type    | Notes                                                                                |
| ---------- | ------- | ------------------------------------------------------------------------------------ |
| `id`       | bigint  | PK                                                                                   |
| `uuid`     | uuid    | External identifier                                                                  |
| `skill_id` | bigint  | FK `skills.id` ON DELETE CASCADE                                                     |
| `path`     | text    | NOT NULL — relative path within the skill (`SKILL.md`, `references/api.md`)          |
| `content`  | text    | NOT NULL — full file body                                                            |
| `is_entry` | boolean | NOT NULL, default false — exactly one row per skill marks the entry file (`SKILL.md`) |

#### `agent_skill_assignments`

| Column     | Type   | Notes                                                                          |
| ---------- | ------ | ------------------------------------------------------------------------------ |
| `agent_id` | bigint | FK `agent_registrations.id` ON DELETE CASCADE                                  |
| `skill_id` | bigint | FK `skills.id` ON DELETE CASCADE                                               |

PRIMARY KEY `(agent_id, skill_id)`. Only used when `skills.is_global = false` — global skills bypass this table entirely.

---

### Scoping

Skills exist in two tiers, and an agent's effective skill set at run time is the union of the two.

**Global (`is_global = true`).** The "operating manual" tier. Every managed agent receives every active global skill. This is the right tier for material that describes Calseta itself — the platform's APIs, tools, conventions, and finding format. The bundled `calseta` skill is global by construction. Today's lab uses only this tier.

**Assigned (`agent_skill_assignments`).** The specialization tier. A skill is created with `is_global = false` and explicitly assigned to one or more agents. This is where an operator declares "this triage agent specializes in account-compromise — give it the IR runbook"; "this enrichment agent owns Sentinel queries — give it the KQL cheatsheet". Assignment is an operator extensibility hook; without it the entire system would either over-share (everything global) or under-share (nothing reusable).

A skill's tier is mutable: an operator can flip `is_global` to broaden a previously specialized skill across the fleet, and the next run will pick it up.

---

### Runtime Injection

Injection happens once per run, before adapter invocation, in `app/runtime/engine.py:_inject_skills_ephemeral`.

1. The engine queries the skill repository for the union of `get_global_skills()` and `get_agent_skills(agent.id)`, deduplicated by skill ID.
2. It creates an ephemeral temp directory with a random suffix (`/tmp/calseta-skills-<random>/`).
3. For every file on every assigned skill, it writes `<tmpdir>/<skill_slug>/<path>` with the file's content.
4. The path is returned to the engine, which passes it to the adapter and registers cleanup in the run's `finally` block (`shutil.rmtree(..., ignore_errors=True)`). No state outlives the run.

For `claude_code` adapter runs, the temp dir is intended to be passed as `--add-dir <tmpdir>`, which makes every file inside it readable by the agent without entering its context until the agent itself decides to read one. For API adapters that lack a filesystem affordance, the entry file (`SKILL.md`) is inlined into Layer 3 of the system prompt and non-entry files are referenced by path.

**Implementation gap.** As of 2026-05-04 the engine writes the temp dir but the `claude_code` adapter does not yet pass `--add-dir`. The bundled skill content reaches the agent only via inlining for the API adapters; for `claude_code` runs the directory is materialized but unreferenced. This is tracked as Wave 5 chunk **S14** in `docs/plans/2026-04-15-agent-runtime-hardening.md` and must close before claiming the SOC operating manual is fully wired in for `claude_code`.

---

### Source-of-Truth Distinction

Skills come from two lineages and the data model does not yet distinguish them at the column level.

**Bundled.** Directories under `app/skills/<slug>/` in this repo. Versioned with the codebase, ship in releases, and are the contract Calseta authors maintain. The lab seeder (`app/seed/sandbox_control_plane.py:_seed_bundled_skills`) walks `app/skills/<slug>/` on lab bootstrap and upserts each directory as a global skill row, with `SKILL.md` flagged `is_entry=true` and every other file written verbatim. The seeder is non-destructive: it upserts and never deletes operator-created skills.

**Operator-created.** Skills authored entirely through the API or UI. They live only in the database. The seeder leaves them alone.

The two lineages are distinguished today by *origin only* — there is no `source` column on `skills`. A bundled skill that an operator has edited locally is indistinguishable in the schema from a wholly operator-authored skill. **Recommendation (follow-up):** add `source` to `skills` with values `bundled` and `operator`, and add `is_modified` to flag operator edits to bundled rows. This unblocks an "upgrade bundled skills" UX without overwriting operator changes.

A universal startup loader — running outside the lab seeder so production self-hosters also get bundled skills on boot — is still pending and tracked as Wave 5 chunk **S14**.

---

### API Surface

All routes live under `/v1/` and are implemented in `app/api/v1/skills.py`.

- `POST /v1/skills` — create a skill (operator authoring).
- `GET /v1/skills` — list all skills with metadata.
- `GET /v1/skills/{uuid}` — fetch a single skill including its file tree.
- `PATCH /v1/skills/{uuid}` — update name, description, `is_active`, `is_global`.
- `DELETE /v1/skills/{uuid}` — delete the skill and cascade its files and assignments.
- `GET /v1/skills/{uuid}/files` — list files on a skill.
- `PUT /v1/skills/{uuid}/files` — upsert a file by `path` (creates or replaces content; `is_entry` flag respected).
- `DELETE /v1/skills/{uuid}/files` — delete a file by path.
- `PUT /v1/agents/{uuid}/skills` — sync the assigned skill set for an agent (whole-set replace; the body is the desired list of skill UUIDs).

Authentication is the standard API key path. Mutating routes require operator scope.

---

### Operator Workflow

A. **Create.** `POST /v1/skills` with `{slug, name, description, is_global}`. Returns the new skill's UUID. Then upsert files via `PUT /v1/skills/{uuid}/files` for every entry, marking the canonical `SKILL.md` with `is_entry: true`.

B. **Assign to one agent.** `PUT /v1/agents/{agent_uuid}/skills` with the agent's full intended skill list. The endpoint replaces the agent's assignment set wholesale; partial-update is by design out of scope.

C. **Edit content.** `PUT /v1/skills/{uuid}/files` with the same `path` overwrites the file's `content` in place. Updates take effect on the next run — there is no in-flight injection refresh.

D. **Delete a file.** `DELETE /v1/skills/{uuid}/files` with the path. Note the entry file cannot be removed without removing the skill.

E. **Revoke an assignment.** Re-`PUT /v1/agents/{agent_uuid}/skills` with the skill omitted. To make the skill global instead, `PATCH /v1/skills/{uuid}` with `is_global: true`.

---

### Bundled Skill Registration

For a Calseta maintainer adding a new bundled skill to the repo:

1. Create the directory `app/skills/<slug>/`.
2. Write `SKILL.md` (the entry file) and any helper files (`references/`, `examples/`, etc.).
3. Add the slug to `_BUNDLED_SKILLS` in `app/seed/sandbox_control_plane.py:_seed_bundled_skills`.
4. Run the lab seeder to upsert the row in the lab database.

Once Wave 5 S14 lands, step 3 will collapse: the universal loader will discover bundled skills by walking `app/skills/` directly, removing the manual registration list.

---

### Out of Scope (Current)

- **Bundle import/export.** Operators cannot export a skill as a tarball or import one from a peer's instance. Sharing happens via copy-paste through the UI.
- **File-level version history.** `skill_files` has no revision table. Edits overwrite.
- **Skill dependencies.** A skill cannot declare "I depend on skill X." If an author needs that they inline the dependency content.
- **Content sandboxing.** Skill content is written verbatim into the agent's filesystem (or system prompt). A malicious skill author with mutating-scope API key access can prompt-inject the agent. This is a known security concern that lives in **Wave 5 S7** (prompt-injection escaping for all injected content); skills inherit whatever protections that chunk lands.
- **Per-run skill subsetting.** All assigned + global skills are injected on every run. There is no "use skill X only for high-severity alerts" gating.

---

### Open Questions

1. **Reload semantics.** Bundled skills today require an operator restart (and a re-run of the lab seeder) to pick up edits made on disk. Should the runtime support a file watcher in dev, an operator-triggered `POST /v1/skills/reload-bundled` endpoint, or remain restart-only? File-watching adds operational surface; the endpoint is cheap and explicit.
2. **Override vs. fork.** When an operator wants to change a bundled skill — say, replace the default IR runbook's escalation contacts — should they edit the bundled row in place (and risk seeder collision on the next release), or should the system require them to fork it into a new operator-source skill? A `source` column plus a `forked_from` FK makes the second option clean.
3. **Backend convergence with Memory.** Memory pages and skill files are structurally near-identical: markdown attached to an agent. The two systems were designed independently and now run in parallel. Should they consolidate onto a single backend (e.g., extend `knowledge_base_pages` with a `kind` column), or is the conceptual distinction (persistent operating manual vs. learned context) worth the schema separation?
