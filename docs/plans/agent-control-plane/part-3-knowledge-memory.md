# Part 3: Knowledge & Memory

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 3: Knowledge & Memory

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 6

---

### Data Model

#### `knowledge_base_pages` (NEW)


| Column                   | Type        | Notes                                                                                                                                                                  |
| ------------------------ | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                     | uuid        | PK                                                                                                                                                                     |
| `slug`                   | text        | NOT NULL, UNIQUE — URL-friendly identifier ("credential-theft-runbook", "siem-query-syntax")                                                                           |
| `title`                  | text        | NOT NULL                                                                                                                                                               |
| `body`                   | text        | NOT NULL — markdown content                                                                                                                                            |
| `folder`                 | text        | NOT NULL, default '/' — hierarchical path ("/runbooks", "/policies", "/integrations")                                                                                  |
| `format`                 | text        | NOT NULL, default 'markdown'                                                                                                                                           |
| `status`                 | enum        | `published`, `draft`, `archived`                                                                                                                                       |
| `inject_scope`           | jsonb       | NULL — injection targeting rules. NULL = not injectable. Examples: `{"global": true}`, `{"roles": ["triage", "investigation"]}`, `{"agent_ids": ["uuid-1", "uuid-2"]}` |
| `inject_priority`        | int         | NOT NULL, default 0 — higher = injected first when token budget is tight                                                                                               |
| `inject_pinned`          | boolean     | NOT NULL, default false — pinned pages are always injected regardless of token budget                                                                                  |
| `sync_source`            | jsonb       | NULL — external sync config. NULL = locally authored. See External Sync below.                                                                                         |
| `sync_last_hash`         | text        | NULL — hash of last synced content (for change detection)                                                                                                              |
| `synced_at`              | timestamptz | NULL — last successful sync                                                                                                                                            |
| `created_by_agent_id`    | int         | NULL — FK `agent_registrations.id`                                                                                                                                     |
| `created_by_operator`    | text        | NULL                                                                                                                                                                   |
| `updated_by_agent_id`    | int         | NULL                                                                                                                                                                   |
| `updated_by_operator`    | text        | NULL                                                                                                                                                                   |
| `latest_revision_id`     | uuid        | NULL — FK `kb_page_revisions.id`                                                                                                                                       |
| `latest_revision_number` | int         | NOT NULL, default 1                                                                                                                                                    |
| `token_count`            | int         | NULL — estimated token count for budget planning                                                                                                                       |
| `metadata`               | jsonb       | NULL — page-type-specific metadata. For memory pages: `{ "memory_type": "entity_profile|codebase_map|investigation_summary|pattern|preference", "staleness_ttl_hours": int, "source_hash": str }`. For regular KB pages: `{ "tags": [str], "category": str }` |
| `created_at`             | timestamptz | NOT NULL                                                                                                                                                               |
| `updated_at`             | timestamptz | NOT NULL                                                                                                                                                               |


#### `kb_page_revisions` (NEW)

Revision history for every page edit.


| Column            | Type        | Notes                                     |
| ----------------- | ----------- | ----------------------------------------- |
| `id`              | uuid        | PK                                        |
| `page_id`         | uuid        | FK `knowledge_base_pages.id`, NOT NULL    |
| `revision_number` | int         | NOT NULL                                  |
| `body`            | text        | NOT NULL — full content at this revision  |
| `change_summary`  | text        | NULL — what changed                       |
| `author_agent_id` | int         | NULL                                      |
| `author_operator` | text        | NULL                                      |
| `sync_source_ref` | text        | NULL — external commit SHA or revision ID |
| `created_at`      | timestamptz | NOT NULL                                  |


#### `kb_page_links` (NEW)

Links KB pages to alerts, issues, investigations, and other pages for cross-referencing.


| Column               | Type        | Notes                                              |
| -------------------- | ----------- | -------------------------------------------------- |
| `id`                 | uuid        | PK                                                 |
| `page_id`            | uuid        | FK `knowledge_base_pages.id`, NOT NULL             |
| `linked_entity_type` | enum        | `alert`, `issue`, `page`, `agent`, `campaign`      |
| `linked_entity_id`   | uuid        | NOT NULL                                           |
| `link_type`          | enum        | `reference`, `source`, `generated_from`, `related` |
| `created_at`         | timestamptz | NOT NULL                                           |

UNIQUE constraint: `(page_id, linked_entity_type, linked_entity_id)` — prevents duplicate links from the same page to the same entity.

**Valid `link_type` combinations by entity:**
- `alert`: all types valid (`reference`, `source`, `generated_from`, `related`)
- `issue`: `reference`, `generated_from`, `related`
- `page`: `reference`, `generated_from`, `related` (wikilinks always use `reference`)
- `agent`: `reference`, `related`
- `campaign`: `reference`, `related`

Wikilinks (`[[slug]]`) auto-create `link_type = 'reference'` to `linked_entity_type = 'page'`. `@alert` and `@issue` inline mentions also create `link_type = 'reference'`.

> Cross-ref: `linked_entity_type = 'issue'` references issues from [Part 4]. `linked_entity_type = 'campaign'` references campaigns from [Part 4].

---

### Knowledge Base System

Calseta needs a structured knowledge base where agents and operators store, discover, and inject organizational knowledge. This unifies several needs: durable work products, injectable agent context, external knowledge sync, and cross-investigation learning.

#### Design Principles

1. **Markdown-native** — pages are markdown. Agents write markdown naturally. Operators read markdown easily.
2. **Context-injectable** — pages can be tagged for automatic injection into agent prompts (Layer 3 of prompt construction).
3. **Externally syncable** — pages can be read-only mirrors of GitHub wikis, Confluence spaces, or Notion databases.
4. **Agent-writable** — agents can create and update pages via tools, building organizational knowledge over time.
5. **Searchable** — full-text and semantic search across all pages.

> Cross-ref: Layer 3 of the 6-layer prompt construction system is in [Part 1: Agent Control Plane (Core Runtime)].

#### Context Injection Flow

When the runtime engine constructs an agent's prompt (Layer 3), it resolves injectable KB pages:

```python
def resolve_kb_context(agent: AgentRegistration) -> list[KBPage]:
    """Resolve KB pages to inject into this agent's prompt."""
    pages = []

    # 1. Global pages (inject_scope.global = true)
    pages += get_pages_where(inject_scope__global=True, status='published')

    # 2. Role-scoped pages (inject_scope.roles contains agent.role)
    pages += get_pages_where(inject_scope__roles__contains=agent.role, status='published')

    # 3. Agent-specific pages (inject_scope.agent_ids contains agent.id)
    pages += get_pages_where(inject_scope__agent_ids__contains=str(agent.id), status='published')

    # 4. Deduplicate, sort by: pinned first, then inject_priority DESC (range: 0–100; default 0), then updated_at DESC as tiebreaker
    # inject_priority range: 0 (default) to 100 (highest). Two pages with the same inject_priority are ordered by recency.
    pages = deduplicate_and_sort(pages)

    # 5. Token budget enforcement
    budget = agent.context_window_size * KB_CONTEXT_BUDGET_PCT  # e.g., 20%
    selected = []
    total_tokens = 0
    for page in pages:
        if page.inject_pinned or total_tokens + page.token_count <= budget:
            selected.append(page)
            total_tokens += page.token_count
    return selected
```

Each selected page is injected as:

```xml
<context_document title="Credential Theft Runbook" slug="credential-theft-runbook" updated="2026-03-15">
[page body in markdown]
</context_document>
```

#### External Sync

Pages can be read-only mirrors of external knowledge bases. Sync is pull-based (Calseta fetches from source on schedule).

##### Supported Sync Sources (Phase 1)

Phase 1 supports three sync sources: **GitHub**, **Confluence**, and **URL**. Notion is deferred to Phase 8+.

| Source         | `sync_source` config                                                                                            | Sync mechanism                                                                                                                                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GitHub**     | `{ "type": "github", "repo": "org/repo", "path": "docs/runbooks/credential-theft.md", "branch": "main" }`       | GitHub API (`GET /repos/{owner}/{repo}/contents/{path}`). Polls on schedule. Private repos require a `secret_ref` for a GitHub PAT with `repo:read` scope (or fine-grained token with `Contents: read`).                      |
| **GitHub Wiki**| `{ "type": "github_wiki", "repo": "org/repo", "page": "Credential-Theft-Runbook" }`                             | Clone wiki repo via git (wikis are separate repos at `{repo}.wiki.git`), read the `.md` file. Same PAT required for private repos.                                                                                            |
| **Confluence** | `{ "type": "confluence", "space_key": "SEC", "page_id": "12345", "base_url": "https://company.atlassian.net" }` | Confluence REST API (`GET /wiki/rest/api/content/{id}?expand=body.storage`). **Format conversion:** Confluence stores content in Atlassian Document Format (ADF/storage XML), not markdown. Calseta converts ADF → markdown using a `ConfluenceToMarkdown` converter class. For write-back (bidirectional sync), Calseta converts markdown → ADF. Use `atlassian-python-api` for API calls. API token requires `read:confluence-content.all` scope. |
| **URL**        | `{ "type": "url", "url": "https://example.com/docs/runbook" }`                                                  | HTTP GET. Uses **markitdown** (already a v1 Calseta dependency) to convert any webpage to markdown — handles HTML, PDFs, and raw markdown URLs. This means any publicly accessible web page or internal documentation URL can be synced. |

> **Notion sync:** Deferred to Phase 8+. The Notion API returns page blocks in a proprietary JSON format that requires significant conversion work. GitHub and Confluence cover the majority of enterprise documentation workflows.

> **ADF ↔ Markdown conversion:** Confluence's ADF format covers headings, lists, tables, code blocks, and inline formatting. Common edge cases: Confluence macros (e.g., `{code}`, `{panel}`) convert to fenced code blocks and blockquotes respectively. Internal Confluence page links convert to KB page wikilink format (`[[page-slug]]`) on pull. On write-back (bidirectional sync), wikilinks resolve to Confluence page IDs via title lookup, with best-effort matching.


##### Sync Scheduler

A Procrastinate periodic task (`sync_kb_pages_task`) runs on a configurable interval (default: every 6 hours):

1. Scan all pages where `sync_source IS NOT NULL` and `status IN ('published', 'sync_error')` (retry errored pages)
2. For each page: validate `sync_source` config (required fields present, `secret_ref` resolves) — if invalid, log `kb.page_synced` event with `outcome=config_invalid`, skip
3. Fetch from source, compute content hash
4. If hash differs from `sync_last_hash`: update body, create revision, update hash, set `synced_at`, log `kb.page_synced` event with `outcome=updated`, `old_hash`, `new_hash`
5. If hash unchanged: update `synced_at`, log `kb.page_synced` event with `outcome=no_change`
6. If fetch fails (network error, auth error, not found): log `kb.page_synced` event with `outcome=fetch_failed`, `error_message`; set page `status = 'sync_error'`; do NOT overwrite local content

**Sync error recovery:** Pages with `status = 'sync_error'` are retried on each scheduler run. After 3 consecutive failures, the page is deprioritized (skipped for 24h) to avoid flooding the scheduler. Operator must resolve the root cause (fix credentials, update `sync_source` config) and manually re-trigger sync or reset the error state.

**Concurrency policy:** `skip_if_active` — if `sync_kb_pages_task` is already running when the next interval fires, Procrastinate skips the queued invocation to prevent overlapping syncs.

Sync can also be triggered manually: `POST /api/v1/kb/sync` (all pages, returns 202 with job_id) or `POST /api/v1/kb/{slug}/sync` (single page, returns 200 with sync result).

**Activity log events for sync:**
- `kb.page_synced` — logged for every page on every sync run. `references` JSONB includes `{ outcome, old_hash, new_hash, revision_id, error_message }`. Actor type: `system`.

**Settings UI:** The sync scheduler interval and global sync on/off toggle are surfaced in the settings UI at `/control-plane/settings/kb-sync`. These are DB-driven platform settings (stored in `platform_settings`) so they can be changed at runtime without restart. Per-page sync intervals (override the global default) are configurable from the KB page editor sidebar.

##### Sync Credentials

External sync sources that require authentication (GitHub private repos, Confluence, Notion) reference credentials via the secrets system. The `sync_source` config includes a `secret_ref` for the API key/token:

> Cross-ref: See [Part 5: Platform Operations] for the secrets system and `secret_ref` pattern.

```json
{
  "type": "confluence",
  "space_key": "SEC",
  "page_id": "12345",
  "base_url": "https://company.atlassian.net",
  "auth": { "type": "secret_ref", "secret_name": "confluence_api_token" }
}
```

##### Bidirectional Confluence Sync (Phase 8+)

The default sync model is pull-only (Calseta fetches from Confluence). Bidirectional sync adds write-back: when a KB page linked to a Confluence page is updated in Calseta, Calseta pushes the change back to Confluence.

**Opt-in per page.** Bidirectional sync is disabled by default. Enabled by setting `sync_source.bidirectional: true` on a page. Pages without this flag remain pull-only.

```json
{
  "type": "confluence",
  "space_key": "SEC",
  "page_id": "12345",
  "base_url": "https://company.atlassian.net",
  "bidirectional": true,
  "auth": { "type": "secret_ref", "secret_name": "confluence_api_token" }
}
```

**Write-back flow:**

1. Operator (or agent) updates a KB page in Calseta
2. If `sync_source.bidirectional = true`: Calseta converts markdown → Confluence storage format (ADF/wiki markup)
3. `PUT /wiki/rest/api/content/{page_id}` with updated body + incremented version number
4. On success: update `sync_last_hash`, create `kb_page_revisions` entry with `sync_source_ref = confluence_version_id`
5. On failure: log error to activity log, mark page with `sync_error` status, notify operator

**Conflict resolution:**

Conflicts occur when Confluence was updated externally between the last pull and the write-back attempt. Strategy: **Calseta-wins by default** (overwrite Confluence with Calseta's version). The previous Confluence version is preserved in Calseta's revision history, so nothing is lost.

A future `conflict_strategy` config option can be added: `calseta_wins` (default) | `confluence_wins` | `manual` (flag conflict, block write until operator resolves).

**Format conversion:**

Calseta markdown → Confluence storage format requires:

- Heading levels (`##` → `<h2>`)
- Code blocks (fenced → `<code>` macro)
- Tables (GFM → Confluence table markup)
- Internal wikilinks → Confluence page links (best-effort, may not resolve)

Use a dedicated `MarkdownToConfluence` converter class. The reverse (Confluence storage → markdown) already exists for pull sync.

**Permissions required:**

The Confluence API token must have `write` permission on the target space. Recommend a dedicated service account (not a personal token) to avoid sync failures on token rotation.

**What doesn't sync bidirectionally:**

- Comments (Confluence comments are not synced to Calseta)
- Confluence page metadata (labels, watchers, space permissions)
- Attachments (pull-sync only for now)

#### Agent-Writable Pages

Agents create and update KB pages via tools:

```
create_kb_page     — Create a new KB page (managed tier)
update_kb_page     — Update an existing KB page (managed tier)
search_kb          — Search KB pages by keyword or semantic query (safe tier)
get_kb_page        — Read a KB page by slug (safe tier)
link_kb_page       — Link a KB page to an alert, issue, or other entity (managed tier)
```

**Common agent-authored pages:**

- Investigation summaries that become reusable knowledge ("TOR Exit Node Investigation Playbook" generated from a real investigation)
- Entity profiles built over time ("[jsmith@corp.com](mailto:jsmith@corp.com) Risk Profile" updated across multiple investigations)
- Detection rule documentation ("Rule XYZ: Purpose, Logic, Known FPs")
- Integration-specific query templates ("Splunk Queries for Credential Theft")

#### Search

Two search modes:

1. **Full-text search** — PostgreSQL `tsvector` index on `body` column. Fast, keyword-based.
2. **Semantic search** (Phase 8+) — Vector embeddings stored in `pgvector` column. Finds conceptually similar pages even when wording differs. Uses the same embedding model as Calseta's existing enrichment pipeline (if available).

```
GET /api/v1/kb/search?q=credential+theft+runbook          # full-text
GET /api/v1/kb/search?q=how+to+investigate+stolen+creds&mode=semantic  # semantic (Phase 8+)
```

#### KB API Surface

```
POST   /api/v1/kb                                  Create page
GET    /api/v1/kb                                  List pages (filterable by folder, status, inject_scope, sync_source)
GET    /api/v1/kb/{slug}                           Get page by slug
PATCH  /api/v1/kb/{slug}                           Update page
DELETE /api/v1/kb/{slug}                           Delete page (or archive)
GET    /api/v1/kb/{slug}/revisions                 List revisions
GET    /api/v1/kb/{slug}/revisions/{rev}           Get specific revision
POST   /api/v1/kb/{slug}/links                     Link page to entity
GET    /api/v1/kb/search                           Search pages
POST   /api/v1/kb/sync                             Trigger sync for all external pages
POST   /api/v1/kb/{slug}/sync                      Trigger sync for single page
GET    /api/v1/kb/folders                           List folder hierarchy
```

#### KB Operator UI Design

> **Reference implementation:** Cabinet (`/Users/jorgecastro/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Calseta/Dev/cabinet`) — a local open-source AI-first KB with the exact UI patterns described here. Cherry-pick patterns and reference components — do not copy code wholesale.
>
> **Key Cabinet components to reference (not copy):**
> - Sidebar + folder tree: `cabinet/src/components/sidebar/sidebar.tsx` (280px fixed, collapsible), `tree-view.tsx`, `tree-node.tsx` — recursive nesting with depth-based indentation, expand/collapse chevrons, drag-and-drop reordering, context menu per node (Add Sub Page, Rename, Delete), type-specific icons (folder, PDF, CSV, website)
> - Search: `cabinet/src/components/search/search-dialog.tsx` — `Cmd+K` global shortcut, 200ms debounced search, tag filtering with clickable pills, arrow key navigation, "Ask AI" fallback when no results
> - Editor: `cabinet/src/components/editor/editor.tsx` (Tiptap), `editor-toolbar.tsx` (H1/H2/H3, bold/italic, code blocks, lists, undo/redo)
> - Version history: `cabinet/src/components/editor/version-history.tsx` — side-by-side diff, git-backed, "Restore to this version" (creates new revision, never destroys history)
> - App shell layout: `cabinet/src/components/layout/app-shell.tsx` — 3-panel layout (sidebar | content | optional right panel), Zustand state management (`tree-store.ts`, `editor-store.ts`)
> - Save status: `editor-store.ts` save state (idle/saving/saved/error) — same pattern for Calseta's auto-save
>
> **KB is a top-level nav item.** The Knowledge Base is not just an agent configuration feature — it's the SOC's primary knowledge repository (runbooks, IR plans, SOPs, detection rule docs, entity profiles) that *also* powers agentic context injection. Human operators browse it daily; agents read from it on every invocation. Route: `/kb` (top-level), not `/control-plane/kb`. The control plane settings for injection scope and sync config are accessible from within KB pages, but the KB itself is a first-class destination in the nav alongside the control plane.
>
> **Navigation structure:**
> ```
> /kb                    ← Top-level KB browser (folder tree + page list + search)
> /kb/{slug}             ← KB page detail (rendered + metadata + revision history)
> /kb/{slug}/edit        ← KB page editor
> /control-plane         ← Agent control plane (dashboard, agents, queue, approvals, etc.)
> ```

The KB operator UI surfaces at `/kb` as a top-level route. Design guidance:

**Folder tree sidebar**

- Left panel: hierarchical folder tree driven by `GET /api/v1/kb/folders` (reference: `cabinet/src/components/sidebar/tree-view.tsx`)
- Clicking a folder filters the page list to that path
- Folders are virtual (derived from `folder` column) — no separate folder entities needed
- Inline "New page" button per folder; context menu per node (Add Sub Page, Rename, Move, Delete)
- Drag-and-drop to reorder and reparent pages (updates `folder` column)

**Page list view**

- Title, folder path, last updated, status badge (published / draft / archived), sync source indicator
- Fuzzy search on title + body (reference: `cabinet/src/components/search/search-dialog.tsx` — `Cmd+K` shortcut, debounced, tag filtering)
- Filter by inject_scope (global / role-scoped / agent-specific / not injectable)
- "Ask AI" fallback in search when no results — queries agent memory + KB semantically (Phase 8+)

**Page editor**

- Use **Tiptap** for WYSIWYG editing with markdown compatibility (reference: `cabinet/src/components/editor/editor.tsx`, `editor-toolbar.tsx`)
  - Slash commands (`/heading`, `/code`, `/table`, `/callout`)
  - Inline markdown shortcuts (`##` → heading, ` ``` ` → code block)
  - Tables with column resize
- Sidebar panel: inject_scope picker, inject_priority, inject_pinned toggle, sync_source config, token count estimate
- Auto-save on keystroke with debounce (optimistic, show "saving..." indicator — reference: Cabinet's `editor-store.ts` save state)
- Markdown source toggle (WYSIWYG ↔ raw markdown)

**@ Mentions**

Type `@` in the editor to reference other entities inline. Uses Tiptap's mention extension with a typeahead dropdown.


| Trigger               | Resolves to         | Example                     |
| --------------------- | ------------------- | --------------------------- |
| `@` + page slug/title | KB page link        | `@credential-theft-runbook` |
| `@agent:`             | Agent registration  | `@agent:triage-specialist`  |
| `@alert:`             | Alert by ID         | `@alert:abc123`             |
| `@issue:`             | Issue by identifier | `@issue:CAL-042`            |


Mentions render as styled chips in the editor. On save, Calseta auto-creates `kb_page_links` entries for any `@page` mentions — keeping the link graph up to date without manual wiring. `@agent`, `@alert`, and `@issue` mentions use the same `kb_page_links` table with the appropriate `linked_entity_type`.

Agents writing KB pages via `create_kb_page` / `update_kb_page` tools can include `[[slug]]`-style wikilinks in markdown (same semantic as `@page` mentions) — the API resolves these to `kb_page_links` on save.

> **Future: extend @ mentions to alert activity and issue comments**
>
> The KB editor is the first surface for @ mentions, but the same pattern should extend to any rich-text input in the operator UI where collaboration happens. Two immediate candidates:
>
> - **Alert activity feed** — Each alert has an activity tab showing an audit trail (agent invocations, action proposals, status changes). Adding a freeform comment input here, with @ mention support, turns it into a lightweight incident collaboration thread. Operators can tag teammates (`@jorge`), link related alerts (`@alert:abc456`), or reference playbooks (`@credential-theft-runbook`) without leaving the alert context. Comments become first-class `activity_log` entries with `event_type: "operator_comment"`.
> - **Issue comments** — Issues already have `agent_issue_comments` and the `add_issue_comment` MCP tool. The operator UI comment input should use the same Tiptap mention extension so operators and agents cross-reference the same entity space.
>
> The mention resolution logic (typeahead, chip rendering, `kb_page_links` side effects) is the same across surfaces. The Tiptap mention extension is reusable — the only surface-specific work is wiring the save handler to the right endpoint (`POST /api/v1/alerts/{id}/comments` vs `POST /api/v1/issues/{id}/comments`).

**Revision history / diff viewer**

- Revision list in a right-side drawer: revision number, author, timestamp, change_summary
- Side-by-side or unified diff view between any two revisions
- "Restore to this version" button (creates a new revision — never destroys history)
- For synced pages: show external commit SHA / Confluence version ID alongside Calseta revision

**Sync status indicators**

- Status badge per page: `synced`, `pending`, `error`, `bidirectional`
- Last synced timestamp tooltip
- "Sync now" button triggers `POST /api/v1/kb/{slug}/sync`
- Error state shows last error message inline

---

### Agent Persistent Memory

Agents build knowledge over time. A security agent that scans a codebase, maps a network topology, or profiles user behavior shouldn't re-learn this on every invocation. The persistent memory system lets agents store and retrieve durable facts.

#### Design

Memory is a specialized subset of the Knowledge Base — agent-writable, agent-readable, with automatic injection into prompt context. The key difference from general KB pages: memory is **private by default** and **agent-managed** (agents decide what to remember, the platform manages injection and staleness).

#### Memory Storage

Memory entries are stored in the existing `knowledge_base_pages` table with special conventions:

- `folder`: `/memory/agents/{agent_id}/` (agent-private) or `/memory/shared/` (promoted to shared)
- `inject_scope`: auto-set to target the owning agent. Shared memory auto-scoped to relevant roles.
- `status`: `published` (active memory) or `archived` (superseded/stale)
- `metadata`: includes `memory_type` (entity_profile, codebase_map, investigation_summary, pattern, preference), `staleness_ttl_hours`, `source_hash` (for invalidation)

#### Memory Tools (Agent-Facing)

```
save_memory        — Store a memory entry (managed tier). Params: title, body, memory_type, ttl_hours, source_context.
recall_memory      — Search agent's memory entries (safe tier). Params: query (keyword or semantic).
update_memory      — Update an existing memory entry (managed tier). Supersedes previous version.
promote_memory     — Promote private memory to shared (managed tier, requires operator approval if configured). Params: memory_id, reason.
list_memories      — List agent's memory entries by type/recency (safe tier).
```

#### Memory Lifecycle

```
Agent creates memory ("save_memory")
  → stored in KB with agent-private scope
  → injected into Layer 6 of prompt construction on future heartbeats
  → ...
  → TTL expires or source changes
  → runtime marks as stale (not deleted, just deprioritized in injection)
  → agent can refresh (re-scan, update) or archive
```

> Cross-ref: Memory entries are injected into Layer 6 (Runtime Checkpoint) of the prompt construction system defined in [Part 1].

**Staleness detection:**

- **TTL-based**: each memory entry has a `staleness_ttl_hours`. After TTL, the entry is flagged as potentially stale. It's still available but injected with a `[STALE — last updated X hours ago]` prefix so the agent knows to verify before trusting.
- **Hash-based**: for codebase scans and file-based knowledge, the `source_hash` (e.g., git commit hash, file SHA) is compared at invocation time. If the source changed, the memory is flagged stale.

**`promote_memory` semantics:** Promotion moves a memory page from `/memory/agents/{agent_id}/` to `/memory/shared/` and updates `inject_scope` to `{ "roles": [agent.role] }` (the promoting agent's role) so other agents with the same role benefit. Both folder path and `inject_scope` change — the folder path is the structural indicator, `inject_scope` controls injection routing. When `memory_promotion_requires_approval = true` on the agent's registration, the tool creates a `WorkflowApprovalRequest` (trigger_type: `memory_promotion`) and returns `status=pending` — the page stays private until approved. On approval, folder and scope are updated. On rejection, the page remains private.

**Injection budget:** Memory entries compete for token budget within Layer 6 of prompt construction. Priority order: (1) non-stale > stale, (2) relevant (keyword match against current alert/issue fields) > general, (3) recent > old. Sort algorithm: `ORDER BY (not is_stale) DESC, relevance_score DESC, updated_at DESC`. The runtime greedily selects entries in sorted order until the Layer 6 budget is exhausted. The runtime caps memory injection at a configurable percentage of the context window (default: 5%).

#### Memory vs. Knowledge Base


| Aspect             | Knowledge Base                 | Agent Memory                             |
| ------------------ | ------------------------------ | ---------------------------------------- |
| Primary author     | Operators, external sync       | Agents                                   |
| Default visibility | Published (all can read)       | Private (owning agent only)              |
| Injection          | Explicit (inject_scope tags)   | Automatic (injected into owning agent)   |
| Staleness          | Manual (operator manages)      | Automatic (TTL + hash-based)             |
| Use case           | Runbooks, policies, references | Learned facts, entity profiles, patterns |


Both use the same underlying storage (`knowledge_base_pages`) and revision system. Memory is a convention on top of KB, not a separate system.

#### Memory Architecture Principles

These design principles are derived from analysis of production memory systems (specifically the Claude Code memory architecture). They should guide both the implementation of the memory system and the system prompts given to managed agents.

**1. Memory = index + storage (bandwidth-aware 3-layer design)**

Never conflate the index with the stored content. The memory system operates in three layers:

- **Index (always loaded)** — a pointer file (analogous to `MEMORY.md`) listing what memories exist and one-line hooks. Always injected. Hard cap: ~150 chars/entry, 200 entries max. Exceeding this causes truncation — enforce at write time.
- **Topic files (on-demand)** — full memory content lives in separate KB pages fetched only when the agent determines they're relevant. The index is a map, not a dump.
- **Transcripts (never read, only searched)** — raw conversation history and prior run logs are never injected. They're grep-able for recovery but not loaded into context.

This prevents the failure mode where agents load all memory on every invocation, burning context on irrelevant facts.

**2. Strict write discipline**

Write to the topic file first, then update the index. Never write content directly into the index. This rule is enforced in the memory tools: `save_memory` creates/updates the topic file, then patches the index entry. If the index entry is updated without a corresponding topic file write, that's a bug.

**3. Background memory consolidation (analogous to autoDream)**

Schedule a periodic consolidation task (separate from the agent's investigation loop) that:

- Merges duplicate memory entries about the same entity
- Deduplicates overlapping facts
- Removes contradictions (keeping the more recent / higher-confidence version)
- Converts vague entries → absolute (e.g., "recently seen" → "last seen 2026-03-15")
- Aggressively prunes low-value entries

This runs as a managed background routine with a restricted tool set (read/write memory only) to prevent corruption of the main agent context. Never run consolidation in-band during an investigation.

**4. Staleness is first-class**

The existing TTL + hash-based staleness detection is correct. Additional rule: **if a memory entry conflicts with what the agent observes at runtime, the memory is wrong — not the observation.** Agents must be explicitly instructed (in their system prompt) to treat memory as a hint, not ground truth.

Facts that are derivable from current state are never stored:

- ❌ Code structure, file paths, schema definitions → read the code
- ❌ Debugging session logs, PR history → use git
- ❌ Alert content already in the enriched payload → it's injected fresh each run
- ✅ Learned behavioral patterns ("this user regularly triggers this rule"), entity profiles ("this IP is a known internal scanner"), calibration data ("FP rate for rule X is ~40%")

**5. Retrieval is skeptical**

The agent's system prompt must include: *"Memory is a hint, not truth. Before acting on a recalled fact, verify it against current observable state. If a memory conflicts with what you observe, trust your observation and update the memory."*

This is especially important for security agents where stale threat intel or entity profiles can lead to incorrect verdicts.

**6. Isolation for consolidation**

Memory consolidation (the background cleanup job) runs in a separate `managed` agent invocation with a restricted tool set — memory read/write only, no alert access, no action tools. This prevents the consolidation process from corrupting the main agent's active investigation context or accidentally triggering security actions.

---

---

