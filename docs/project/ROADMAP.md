# Calseta — Roadmap

Future enhancements tracked here. Not committed to a timeline — prioritized as capacity allows.

---

## UI Enhancements

### MITRE ATT&CK Searchable Multi-Select
- Replace freetext chip inputs for tactics, techniques, and sub-techniques with searchable multi-select dropdowns
- Populate from the full MITRE ATT&CK catalog (Enterprise matrix)
- Sub-techniques scoped to their parent technique (e.g. T1059.001 only appears under T1059)
- Applies to: detection rule create modal, detection rule edit modal
- Prerequisite: decide whether to bundle the ATT&CK catalog as static JSON or fetch from MITRE's STIX/TAXII endpoint

### Custom Dashboard Cards
- Allow users to create their own dashboard KPI cards and charts with user-defined names, descriptions, chart types, and data queries
- **Data model**: new `dashboard_cards` table (`uuid`, `name`, `description`, `query`, `chart_type` enum: `kpi`/`bar`/`line`/`pie`/`table`, `config` JSONB for axis labels/colors/thresholds, `position` JSONB for grid coords). Optional `dashboard_card_snapshots` table for cached query results
- **API**: `POST/PATCH/DELETE /v1/dashboard-cards`, `POST /v1/dashboard-cards/preview` (run query and return data without saving)
- **Frontend**: card editor modal (name, description, query input, chart type picker, live preview), generic chart renderer that takes `{ chart_type, data, config }` and renders the appropriate Recharts component
- **Query engine — phased approach**:
  - **Phase 1 — Structured query builder** (recommended starting point): users pick entity (alerts, indicators, workflows, approvals), metric (count, avg, min, max, sum), group-by (severity, status, source, time bucket), and filters (date range, severity, etc.) via a form UI. Backend translates to safe SQLAlchemy queries. No injection risk, predictable performance
  - **Phase 2 — Restricted SQL mode** (optional upgrade): users write raw SQL, validated via AST parsing (`sqlglot`/`sqlparse`). `SELECT`-only allowlist, table/column allowlist (exclude `api_keys`, `auth_config`, `key_hash`), dangerous function blocklist, read-only Postgres role with column-level grants, `statement_timeout` (5s), row limit cap (10,000), rate limiting on query execution
  - **Phase 3 — Domain-specific query language** (optional, highest effort): purpose-built DSL (e.g. `alerts | where severity = "Critical" | count by source | last 30d`), parsed into safe AST and compiled to SQLAlchemy. Highest control over expressiveness but requires building a parser and compiler
- **Security requirements** (non-negotiable for Phase 2+): dedicated read-only Postgres role, column-level grants excluding sensitive data, `statement_timeout`, row count limits, no access to `pg_catalog`/`information_schema`/system functions, rate limiting on execution
- **Design note**: store `query` as JSON in Phase 1 (structured builder output), which can later accept raw SQL strings in Phase 2 — card renderer and API shape remain the same regardless of query engine
