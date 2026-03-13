# AI-Assisted Features — Implementation Plan

**Version:** 1.1
**Target Release:** v1.1
**Created:** 2026-03-13
**Updated:** 2026-03-13
**Status:** In Progress — Wave A complete

---

## Context

Calseta is an AI-native SOC data platform. Its core pipeline (ingest → normalize → enrich → expose) is **deterministic and never consumes LLM tokens**. That principle is unchanged.

However, SOC teams configuring Calseta need help with two labor-intensive tasks:
1. **Tuning detection rules** — analyzing historical alerts to identify false positive patterns and recommending threshold/logic adjustments
2. **Authoring workflows** — writing Python HTTP automation scripts (already partially implemented via `POST /v1/workflows/generate`)

This plan adds **optional AI-assisted configuration tools** on top of the deterministic platform. Calseta works without any LLM configured. Adding a provider unlocks AI assistance for these two use cases.

The plan also adds **per-detection-rule effectiveness metrics** — a purely deterministic feature that's valuable independently and serves as input data for the AI tuning analysis.

### Guiding Principle

> "Calseta works without any LLM. Add one to unlock AI-assisted configuration."

The deterministic pipeline is never altered. LLM features are power tools for humans configuring the platform.

---

## Wave Overview

| Wave | Name | Description | Depends On |
|------|------|-------------|------------|
| **A** | Detection Rule Metrics + Alerts | Per-rule FP/TP rates, volume, trends + DnD metrics tab + alerts tab in UI | MVP complete |
| **B** | LLM Provider Foundation | Multi-provider settings, DB model, CRUD API, settings page | MVP complete |
| **C** | Prompt Management | Editable prompts table, seeded defaults, settings UI | Wave B |
| **D** | AI-Assisted Rule Tuning | Backend analysis service + UI integration on rule detail page | Waves A + C |
| **E** | Enhanced Workflow Authoring | Iterative generation, DB-driven prompts, improved UI | Wave C |

---

## Wave A — Detection Rule Metrics

### Purpose
Surface per-detection-rule effectiveness metrics. Pure SQL aggregation — no LLM, no new dependencies. Valuable independently.

---

### Chunk A.1 — Backend: Detection Rule Metrics Service + API Endpoint

**Files to create/modify:**
- `app/services/detection_rule_metrics.py` (new)
- `app/schemas/detection_rule_metrics.py` (new)
- `app/api/v1/detection_rules.py` (add endpoint)

**What to build:**

New service function `compute_detection_rule_metrics(db, detection_rule_id, from_time, to_time)` following the exact pattern in `app/services/metrics.py`.

**Metrics to compute (all scoped to a single detection rule):**

| Metric | SQL Pattern | Return Type |
|--------|------------|-------------|
| `total_alerts` | `COUNT(alerts) WHERE detection_rule_id = ?` | `int` |
| `alerts_by_status` | `GROUP BY status` | `dict[str, int]` |
| `alerts_by_severity` | `GROUP BY severity` | `dict[str, int]` |
| `false_positive_rate` | `COUNT(close_classification LIKE 'False Positive%') / COUNT(closed)` | `float` |
| `true_positive_rate` | `COUNT(close_classification LIKE 'True Positive%') / COUNT(closed)` | `float` |
| `close_classifications` | `GROUP BY close_classification WHERE status = 'Closed'` | `dict[str, int]` |
| `alerts_over_time` | `GROUP BY date_trunc('day', created_at)` | `list[{date, count}]` |
| `fp_over_time` | `GROUP BY day, filtered to FP close_classification` | `list[{date, count}]` |
| `mtta_seconds` | `AVG(acknowledged_at - created_at)` | `float \| None` |
| `mttc_seconds` | `AVG(closed_at - created_at)` | `float \| None` |
| `active_alerts` | `COUNT WHERE status IN (Open, Triaging, Escalated)` | `int` |
| `severity_distribution` | Same as alerts_by_severity but for active only | `dict[str, int]` |
| `top_indicators` | `JOIN alert_indicators + indicators, GROUP BY (type, value), ORDER BY count DESC LIMIT 10` | `list[{type, value, count, malice}]` |
| `alert_sources` | `GROUP BY source_name` | `dict[str, int]` |

**Response schema** (`DetectionRuleMetricsResponse`):
```python
class DetectionRuleMetricsResponse(BaseModel):
    detection_rule_uuid: uuid.UUID
    detection_rule_name: str
    period_from: datetime
    period_to: datetime
    total_alerts: int
    active_alerts: int
    alerts_by_status: dict[str, int]
    alerts_by_severity: dict[str, int]
    false_positive_rate: float
    true_positive_rate: float
    close_classifications: dict[str, int]
    alerts_over_time: list[dict[str, Any]]
    fp_over_time: list[dict[str, Any]]
    mtta_seconds: float | None
    mttc_seconds: float | None
    severity_distribution: dict[str, int]
    top_indicators: list[dict[str, Any]]
    alert_sources: dict[str, int]
```

**API endpoint:**
```
GET /v1/detection-rules/{uuid}/metrics?from=<iso>&to=<iso>
```
- Defaults: `from` = 30 days ago, `to` = now
- Auth scope: `alerts:read` (reading alert data scoped to a rule)
- Rate limited same as other authed endpoints
- Returns `DataResponse[DetectionRuleMetricsResponse]`

**Implementation notes:**
- Resolve detection rule by UUID → get internal `id` for JOIN
- Return 404 if rule not found
- All queries use the time window filter on `alerts.created_at`
- Follow the exact SQLAlchemy patterns in `app/services/metrics.py` (no ORM relationships, raw `select()`)
- The `top_indicators` query joins `alert_indicators` → `indicators` with `GROUP BY (indicators.type, indicators.value)`, returning count + malice

**Status:** COMPLETE

**Acceptance criteria:**
- [x] Endpoint returns correct metrics for a detection rule with alerts
- [x] Endpoint returns zeroed metrics for a rule with no alerts
- [x] 404 for non-existent rule UUID
- [x] Time window filtering works correctly
- [x] Rate limited and auth-scoped

**Completion notes:**
- `app/services/detection_rule_metrics.py` — 14 SQL queries following `app/services/metrics.py` patterns
- `app/schemas/detection_rule_metrics.py` — `DetectionRuleMetricsResponse` Pydantic schema
- `app/api/v1/detection_rules.py` — `GET /{rule_uuid}/metrics` endpoint added with `from`/`to` query params
- Defaults: from=30 days ago, to=now; 404 if rule not found; `alerts:read` scope; rate limited

---

### Chunk A.2 — Frontend: Detection Rule Metrics Tab with DnD Grid

**Files to create/modify:**
- `ui/src/pages/settings/detection-rules/detail.tsx` (add Metrics tab)
- `ui/src/pages/settings/detection-rules/metrics-tab.tsx` (new — extracted component)
- `ui/src/hooks/use-api.ts` (add `useDetectionRuleMetrics` hook)
- `ui/src/hooks/use-detection-rule-metrics-layout.ts` (new — DnD layout hook)
- `ui/src/lib/types.ts` (add `DetectionRuleMetrics` type)

**What to build:**

A new "Metrics" tab on the detection rule detail page, using the same DnD grid pattern as the main dashboard.

**Step 1: Add TypeScript type** to `lib/types.ts`:
```typescript
export interface DetectionRuleMetrics {
  detection_rule_uuid: string;
  detection_rule_name: string;
  period_from: string;
  period_to: string;
  total_alerts: number;
  active_alerts: number;
  alerts_by_status: Record<string, number>;
  alerts_by_severity: Record<string, number>;
  false_positive_rate: number;
  true_positive_rate: number;
  close_classifications: Record<string, number>;
  alerts_over_time: { date: string; count: number }[];
  fp_over_time: { date: string; count: number }[];
  mtta_seconds: number | null;
  mttc_seconds: number | null;
  severity_distribution: Record<string, number>;
  top_indicators: { type: string; value: string; count: number; malice: string }[];
  alert_sources: Record<string, number>;
}
```

**Step 2: Add React Query hook** to `hooks/use-api.ts`:
```typescript
export function useDetectionRuleMetrics(uuid: string) {
  return useQuery({
    queryKey: ["detection-rule-metrics", uuid],
    queryFn: () => api.get<DataResponse<DetectionRuleMetrics>>(
      `/detection-rules/${uuid}/metrics`
    ),
    enabled: !!uuid,
  });
}
```

**Step 3: Create DnD layout hook** (`use-detection-rule-metrics-layout.ts`):
- Follow exact pattern from `ui/src/hooks/use-dashboard-layout.ts`
- Storage key: `calseta:rule-metrics-grid:v1`
- 12-column grid, same as main dashboard
- Default layout with these cards:

```
Row 0: KPI cards (4 × 3 cols)
  - total-alerts, active-alerts, fp-rate, tp-rate

Row 1: KPI cards (2 × 3 cols + empty)
  - mtta, mttc

Row 2-4: Charts (2 × 6 cols, 3h each)
  - alerts-over-time (line/bar chart), fp-over-time (line/bar chart)

Row 5-7: Charts (2 × 6 cols, 3h each)
  - severity-chart (bar), status-chart (bar)

Row 8-10: Charts/Tables (2 × 6 cols, 3h each)
  - close-classifications (bar), top-indicators (table card)

Row 11-13: Charts (1 × 6 cols, 3h)
  - alert-sources (bar)
```

**Step 4: Create `metrics-tab.tsx`** component:
- Import `Responsive` from `react-grid-layout/legacy`
- Use the layout hook for DnD persistence
- Reuse the same `KpiCard`, `ChartCard` component patterns from dashboard (`ui/src/pages/dashboard/index.tsx`)
- Extract `KpiCard`, `ChartCard`, `StatCard` into shared components at `ui/src/components/dashboard-cards.tsx` if not already shared (check first — they may be inline in dashboard)
- Include Reset Layout button and Refresh button
- Use `useResizeWidth()` pattern from dashboard for responsive width
- Include drag handle SVG (same as dashboard)
- Recharts for all charts (same `tooltipStyle`, `severityColor` patterns)
- `top-indicators` card: render as a small table inside a card (type, value, count, malice badge)
- Show "No alerts for this detection rule" empty state when `total_alerts === 0`

**Step 5: Add tab to `detail.tsx`:**
```tsx
// In the Tabs component, add:
<TabsTrigger value="metrics" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
  <BarChart3 className="h-3.5 w-3.5 mr-1" />
  Metrics
</TabsTrigger>

<TabsContent value="metrics" className="mt-4">
  <DetectionRuleMetricsTab uuid={uuid} />
</TabsContent>
```

**Step 6: Update router search validation** in `router.tsx`:
- The `validateSearch` for detection rule detail already defaults to `"documentation"` — just ensure `"metrics"` is also a valid tab value (it will be, since it's just a string)

**Implementation notes:**
- The `KpiCard` and `ChartCard` patterns are currently **inline** in `dashboard/index.tsx`. Before duplicating, extract them into `ui/src/components/dashboard-cards.tsx` with proper exports. Update the dashboard to import from there.
- Use `formatSeconds()` and `formatPercent()` from `lib/format.ts` for KPI display
- `fp-over-time` chart should overlay on `alerts-over-time` as a stacked or dual-axis chart if feasible, otherwise keep separate

**Status:** COMPLETE

**Acceptance criteria:**
- [x] "Metrics" tab appears on detection rule detail page
- [x] Grid is drag-and-drop, layout persists in localStorage
- [x] Reset Layout button restores defaults
- [x] All 14 metrics render correctly with real data
- [x] Empty state shown when rule has no alerts
- [x] Responsive: works on smaller screens (collapses gracefully)
- [x] Charts use same styling as main dashboard (tooltip, colors, fonts)

**Completion notes:**
- `ui/src/pages/settings/detection-rules/metrics-tab.tsx` — 726 lines, DnD grid with 13 cards (6 KPIs + 6 charts + 1 indicators table)
- Layout hook inlined using `useRuleMetricsLayout` with localStorage key `calseta:rule-metrics-grid:v1`
- `useResizeWidth` hook for responsive width
- KpiCard/ChartCard patterns replicated from dashboard (not extracted to shared — kept inline)
- `ui/src/hooks/use-api.ts` — `useDetectionRuleMetrics(uuid)` hook added
- `ui/src/lib/types.ts` — `DetectionRuleMetrics` interface added
- Tab added to `detail.tsx` with BarChart3 icon

---

### Chunk A.3 — Frontend: Detection Rule Alerts Tab

**Files to create/modify:**
- `app/schemas/alerts.py` (add fields to `AlertSummary`)
- `ui/src/lib/types.ts` (add fields to `AlertSummary` type)
- `ui/src/pages/settings/detection-rules/alerts-tab.tsx` (new)
- `ui/src/pages/settings/detection-rules/detail.tsx` (add tab)

**Backend change — extend `AlertSummary` schema:**

The list endpoint `GET /v1/alerts` currently returns `AlertSummary` which lacks `close_classification`, `closed_at`, and `updated_at`. Add these three fields to `AlertSummary` in `app/schemas/alerts.py`:

```python
class AlertSummary(BaseModel):
    # ... existing fields ...
    close_classification: str | None = None  # NEW
    closed_at: datetime | None = None        # NEW
    updated_at: datetime                     # NEW
```

Since `AlertSummary` uses `from_attributes=True`, these will auto-populate from the ORM model which already has all three columns. No repository or API route changes needed.

Update the TypeScript `AlertSummary` interface in `ui/src/lib/types.ts` to match:
```typescript
export interface AlertSummary {
  // ... existing fields ...
  close_classification: string | null;  // NEW
  closed_at: string | null;             // NEW
  updated_at: string;                   // NEW
}
```

**What to build:**

A new "Alerts" tab on the detection rule detail page showing all alerts associated with that rule. This tab reuses the exact same table pattern as the main alerts list page (`ui/src/pages/alerts/index.tsx`) but:

1. **Pre-filtered** by `detection_rule_uuid` — the UUID is passed as a fixed query parameter to `useAlerts()`; no backend changes needed since `GET /v1/alerts?detection_rule_uuid={uuid}` already works
2. **Additional columns**: Close Classification, Closed At, Created At, Updated At
3. **Same features**: Pagination, sorting, column filtering (status, severity, enrichment, source), resizable columns, loading skeletons

**Step 1: Create `alerts-tab.tsx`:**
- Accept `ruleUuid: string` prop
- Use `useTableState()` with the same filter shape as alerts index
- Call `useAlerts({ ...params, detection_rule_uuid: ruleUuid })`
- Column definitions (expanded from alerts index):

| Column | Key | Width | Sortable | Filterable |
|--------|-----|-------|----------|------------|
| Title | `title` | 320 | Yes | No |
| Status | `status` | 100 | Yes | Yes (4 values) |
| Close Classification | `close_classification` | 180 | No | No |
| Severity | `severity` | 100 | Yes | Yes (6 values) |
| Source | `source` | 110 | Yes | Yes (4 values) |
| Enrichment | `enrichment` | 100 | No | Yes (3 values) |
| Occurred At | `occurred_at` | 155 | Yes | No |
| Closed At | `closed_at` | 155 | No | No |
| Created At | `created_at` | 155 | No | No |

- Render `close_classification` as a styled badge (FP = red tint, TP = green tint, null = dash)
- Render timestamps with `formatDate()`
- Row click navigates to `/alerts/{uuid}` (same as main alerts table)
- Empty state: "No alerts found for this detection rule"
- Refresh button + reset filters button
- Alert count in header: "{N} alerts (filtered)" when filters active

**Step 2: Add tab to `detail.tsx`:**
```tsx
<TabsTrigger value="alerts" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
  <AlertTriangle className="h-3.5 w-3.5 mr-1" />
  Alerts
</TabsTrigger>

<TabsContent value="alerts" className="mt-4">
  <DetectionRuleAlertsTab ruleUuid={uuid} />
</TabsContent>
```

Place the "Alerts" tab between "Documentation" and "Metrics" (order: Documentation, Alerts, Metrics).

**Step 3: Storage key** for resizable columns: `detection-rule-alerts` (distinct from the main alerts table `alerts` key)

**Implementation notes:**
- No new API hooks needed — reuse `useAlerts()` with the `detection_rule_uuid` param
- The `detection_rule_uuid` filter is already implemented in `app/repositories/alert_repository.py` (line ~169)
- No UUID column in this table (redundant since user is already on a detail page — save horizontal space)
- `close_classification` badge color map: `"True Positive*"` → green/teal tint, `"False Positive*"` → red tint, `"Benign Positive*"` → amber tint, `"Undetermined"` / `"Duplicate"` / `"Not Applicable"` → gray, `null` → show dash

**Status:** COMPLETE

**Acceptance criteria:**
- [x] "Alerts" tab appears on detection rule detail page
- [x] Table shows all alerts for the selected detection rule
- [x] Pagination, sorting, and column filters work correctly
- [x] Close Classification column renders with color-coded badges
- [x] Closed At, Created At, Updated At columns render formatted timestamps
- [x] Row click navigates to alert detail page
- [x] Empty state shown when rule has no associated alerts
- [x] Resizable columns with layout persistence
- [x] `AlertSummary` backend schema extended with 3 new fields (non-breaking, additive)

**Completion notes:**
- `ui/src/pages/settings/detection-rules/alerts-tab.tsx` — ~440 lines, full table with ResizableTable
- Column order: Title, Status, Severity, Enrichment, Close Classification, Source, Created At, Closed At, Occurred At
- `app/schemas/alerts.py` — `AlertSummary` extended with `close_classification`, `closed_at`, `updated_at`
- `ui/src/lib/types.ts` — `AlertSummary` interface updated to match
- Reuses existing `useAlerts()` hook with `detection_rule_uuid` param (no new API needed)
- `classificationColor()` helper for badge coloring (TP=teal, FP=red, BP=amber)
- Storage key: `detection-rule-alerts`
- Tab added to `detail.tsx` with Bell icon

---

## Wave B — LLM Provider Foundation

### Purpose
Allow users to configure one or more LLM providers (Anthropic, OpenAI, Azure OpenAI, local/Ollama) via the UI. Encrypted API key storage. Multi-provider support with a concept of "active" provider per use case.

---

### Chunk B.1 — Database Model + Migration

**Files to create/modify:**
- `app/db/models/llm_provider.py` (new)
- `app/db/models/__init__.py` (register model)
- `alembic/versions/XXXX_add_llm_providers.py` (new migration)

**Table: `llm_providers`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `BigInteger` PK | Internal |
| `uuid` | `UUID` | External-facing (UUIDMixin) |
| `provider_type` | `Text NOT NULL` | `anthropic`, `openai`, `azure_openai`, `ollama`, `custom` |
| `display_name` | `Text NOT NULL` | User-facing label, e.g. "My Claude Account" |
| `is_active` | `Boolean NOT NULL DEFAULT true` | Soft disable |
| `api_base_url` | `Text` | Nullable. Required for `azure_openai`, `ollama`, `custom`. Default per provider_type. |
| `default_model` | `Text NOT NULL` | e.g. `claude-sonnet-4-6`, `gpt-4o`, `llama3.1` |
| `auth_config` | `JSONB` | Encrypted at rest using `app/auth/encryption.py` pattern: `{"_encrypted": "<ciphertext>"}`. Plaintext shape: `{"api_key": "sk-..."}` or `{"api_key": "...", "api_version": "2024-02-01"}` for Azure |
| `provider_config` | `JSONB` | Non-secret provider-specific config. E.g. `{"max_tokens": 4096, "temperature": 0.2}` |
| `use_cases` | `Text[] NOT NULL` | Which features this provider is assigned to: `['workflow_generation', 'rule_tuning']`. An empty array means available but not assigned. |
| `created_at` | `TIMESTAMPTZ` | TimestampMixin |
| `updated_at` | `TIMESTAMPTZ` | TimestampMixin |

**Constraints:**
- Unique on `display_name`
- Check: `provider_type IN ('anthropic', 'openai', 'azure_openai', 'ollama', 'custom')`

**Model pattern:** Follow `app/db/models/enrichment_provider.py` exactly (inherit `TimestampMixin`, `UUIDMixin`, `Base`).

**Acceptance criteria:**
- [ ] Migration creates table with all columns and constraints
- [ ] Migration is reversible (downgrade drops table)
- [ ] Model imports cleanly in `__init__.py`

---

### Chunk B.2 — Repository + Schemas

**Files to create/modify:**
- `app/repositories/llm_provider_repository.py` (new)
- `app/schemas/llm_providers.py` (new)

**Repository** — follow `app/repositories/enrichment_provider_repository.py`:
```python
class LLMProviderRepository:
    def __init__(self, db: AsyncSession) -> None: ...
    async def get_by_uuid(self, provider_uuid: UUID) -> LLMProvider | None: ...
    async def get_active_for_use_case(self, use_case: str) -> LLMProvider | None: ...
    async def list(self, *, is_active: bool | None = None, page: int = 1, page_size: int = 50) -> tuple[list[LLMProvider], int]: ...
    async def create(self, **kwargs) -> LLMProvider: ...
    async def patch(self, provider: LLMProvider, updates: dict) -> LLMProvider: ...
    async def delete(self, provider: LLMProvider) -> None: ...
```

Key method: `get_active_for_use_case(use_case)` — returns the first active provider whose `use_cases` array contains the given use case. This is how the workflow generator and rule tuning service resolve their LLM provider at runtime.

**Schemas:**
```python
class LLMProviderCreate(BaseModel):
    provider_type: str  # Literal["anthropic", "openai", "azure_openai", "ollama", "custom"]
    display_name: str = Field(..., min_length=1, max_length=200)
    api_base_url: str | None = None
    default_model: str = Field(..., min_length=1, max_length=100)
    auth_config: dict[str, Any] | None = None  # Contains api_key, encrypted before storage
    provider_config: dict[str, Any] | None = None
    use_cases: list[str] = Field(default_factory=list)

class LLMProviderPatch(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    api_base_url: str | None = None
    default_model: str | None = None
    auth_config: dict[str, Any] | None = None
    provider_config: dict[str, Any] | None = None
    use_cases: list[str] | None = None

class LLMProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: UUID
    provider_type: str
    display_name: str
    is_active: bool
    api_base_url: str | None
    default_model: str
    has_credentials: bool  # Computed: auth_config is not None and not empty
    provider_config: dict[str, Any] | None
    use_cases: list[str]
    created_at: datetime
    updated_at: datetime
    # NOTE: auth_config is NEVER returned in responses
```

**Acceptance criteria:**
- [ ] Repository CRUD operations work correctly
- [ ] `get_active_for_use_case` returns the correct provider
- [ ] Schemas validate provider_type values
- [ ] `auth_config` is never serialized in response schema

---

### Chunk B.3 — API Routes (CRUD)

**Files to create/modify:**
- `app/api/v1/llm_providers.py` (new)
- `app/api/v1/__init__.py` (register router)

**Endpoints:**

| Method | Path | Auth Scope | Description |
|--------|------|-----------|-------------|
| `GET` | `/v1/llm-providers` | `admin` | List all providers |
| `POST` | `/v1/llm-providers` | `admin` | Create provider |
| `GET` | `/v1/llm-providers/{uuid}` | `admin` | Get single provider |
| `PATCH` | `/v1/llm-providers/{uuid}` | `admin` | Update provider |
| `DELETE` | `/v1/llm-providers/{uuid}` | `admin` | Delete provider |
| `POST` | `/v1/llm-providers/{uuid}/test` | `admin` | Test connection (sends a tiny prompt to verify key works) |

**Test connection endpoint:**
- Decrypts `auth_config`
- Based on `provider_type`, sends a minimal request:
  - Anthropic: `POST /v1/messages` with `max_tokens=1`, model from config
  - OpenAI: `POST /v1/chat/completions` with `max_tokens=1`
  - Azure OpenAI: same but with azure base URL + api-version header
  - Ollama: `GET /api/tags` (list models) or `POST /api/generate` with minimal prompt
  - Custom: `GET <api_base_url>` (health check)
- Returns `{"status": "connected", "model": "...", "latency_ms": N}` or `{"status": "error", "message": "..."}`
- Timeout: 10 seconds

**Implementation notes:**
- Follow `app/api/v1/enrichment_providers.py` pattern exactly
- Encrypt `auth_config` before storage using `app/auth/encryption.py`
- Never return `auth_config` in any response
- Rate limited, admin-only
- Register router in `app/api/v1/__init__.py`

**Acceptance criteria:**
- [ ] Full CRUD works
- [ ] API keys are encrypted at rest, never returned in responses
- [ ] Test connection works for Anthropic and OpenAI
- [ ] 404 for non-existent UUID
- [ ] Auth scope enforced (admin only)

---

### Chunk B.4 — Frontend: LLM Providers Settings Page

**Files to create/modify:**
- `ui/src/pages/settings/llm-providers/index.tsx` (new)
- `ui/src/pages/settings/llm-providers/detail.tsx` (new — optional, could be dialog-based)
- `ui/src/hooks/use-api.ts` (add hooks)
- `ui/src/lib/types.ts` (add types)
- `ui/src/router.tsx` (add routes)
- `ui/src/components/layout/sidebar.tsx` or equivalent (add nav item)

**Navigation:**
- Add "AI Providers" under Settings section in sidebar (icon: `Brain` or `Sparkles` from lucide)
- Route: `/settings/ai-providers`

**List page (`index.tsx`):**
- Table/card list of configured providers
- Columns: Display Name, Provider Type (badge), Model, Use Cases (badges), Status (active/inactive badge), Actions
- "Add Provider" button opens create dialog
- Empty state: "No LLM providers configured. Add one to unlock AI-assisted features."

**Create/Edit dialog:**
- Provider Type selector (Anthropic, OpenAI, Azure OpenAI, Ollama, Custom)
- Display Name input
- API Key input (password field, shown only on create/edit, never prefilled)
- API Base URL input (shown for Azure OpenAI, Ollama, Custom; auto-populated defaults for Anthropic/OpenAI)
- Default Model input (with suggestions per provider type — e.g. Anthropic: claude-sonnet-4-6, claude-haiku-4-5; OpenAI: gpt-4o, gpt-4o-mini)
- Use Cases multi-select: Workflow Generation, Rule Tuning Analysis
- Test Connection button (calls `/test` endpoint, shows success/error toast with latency)
- Advanced Settings collapsible: `provider_config` JSON editor (max_tokens, temperature)

**Detail/Edit page or dialog:**
- Same fields as create, but API key shows "••••••• (configured)" if `has_credentials` is true
- "Update API Key" button reveals the password input
- Delete button with confirmation

**Implementation notes:**
- Follow the pattern of `ui/src/pages/settings/enrichment-providers/` exactly
- React Query hooks: `useLLMProviders()`, `useLLMProvider(uuid)`, `useCreateLLMProvider()`, `usePatchLLMProvider()`, `useDeleteLLMProvider()`, `useTestLLMProvider(uuid)`
- Provider type badge colors: Anthropic = amber, OpenAI = green, Azure = blue, Ollama = purple, Custom = gray

**Acceptance criteria:**
- [ ] Settings page lists all LLM providers
- [ ] Create/edit/delete flows work
- [ ] API key is never displayed after creation
- [ ] Test Connection shows success/error with latency
- [ ] Use case assignment works via multi-select
- [ ] Navigation item appears in sidebar

---

### Chunk B.5 — Migrate Workflow Generator to DB-Driven Provider

**Files to modify:**
- `app/services/workflow_generator.py`
- `app/api/v1/workflows.py` (the `/generate` endpoint)

**What to change:**

Currently, `workflow_generator.py` hardcodes:
- `ANTHROPIC_API_KEY` from env
- Anthropic API URL and format
- Model `claude-sonnet-4-6`

Refactor to:
1. Accept a `LLMProvider` (or its decrypted config) instead of `Settings`
2. Create a thin LLM client abstraction:

```python
# app/services/llm_client.py (new)

async def call_llm(
    provider: LLMProvider,  # DB model with decrypted auth
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """Route to the correct provider API and return the text response."""
    if provider.provider_type == "anthropic":
        return await _call_anthropic(provider, system_prompt, user_prompt, max_tokens, temperature)
    elif provider.provider_type in ("openai", "azure_openai"):
        return await _call_openai(provider, system_prompt, user_prompt, max_tokens, temperature)
    elif provider.provider_type == "ollama":
        return await _call_ollama(provider, system_prompt, user_prompt, max_tokens, temperature)
    elif provider.provider_type == "custom":
        return await _call_openai(provider, system_prompt, user_prompt, max_tokens, temperature)  # OpenAI-compatible
    else:
        raise ValueError(f"Unsupported provider type: {provider.provider_type}")
```

3. The `/generate` endpoint resolves the LLM provider:
   - First: try `LLMProviderRepository.get_active_for_use_case("workflow_generation")`
   - Fallback: if no DB provider configured, fall back to `ANTHROPIC_API_KEY` env var (backward compat)
   - If neither: return 503 with clear error message

**Implementation notes:**
- `_call_anthropic()`: same HTTP call as current code, but uses provider's `api_base_url` (default `https://api.anthropic.com`), `default_model`, and decrypted `auth_config.api_key`
- `_call_openai()`: `POST {base_url}/v1/chat/completions` with `{"model": ..., "messages": [{"role": "system", ...}, {"role": "user", ...}], "max_tokens": ...}`
- Azure OpenAI: base URL includes deployment, add `api-version` query param from `auth_config.api_version`
- `_call_ollama()`: `POST {base_url}/api/chat` with `{"model": ..., "messages": [...], "stream": false}`
- All calls use `httpx.AsyncClient` with 60s timeout
- Decrypt `auth_config` at call time using `decrypt_value()` from `app/auth/encryption.py`

**Acceptance criteria:**
- [ ] Workflow generation works with DB-configured Anthropic provider
- [ ] Workflow generation works with OpenAI provider
- [ ] Fallback to `ANTHROPIC_API_KEY` env var when no DB provider exists
- [ ] 503 error with clear message when no LLM available
- [ ] Existing tests still pass

---

## Wave C — Prompt Management

### Purpose
Store system prompts in the database so users can view and edit them. Seed sensible defaults. Surface via settings UI.

---

### Chunk C.1 — Database Model + Migration + Seed

**Files to create/modify:**
- `app/db/models/llm_prompt.py` (new)
- `app/db/models/__init__.py` (register)
- `alembic/versions/XXXX_add_llm_prompts.py` (new migration)
- `app/seed/llm_prompts.py` (new)
- `app/seed/__init__.py` (call prompt seeder)

**Table: `llm_prompts`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `BigInteger` PK | Internal |
| `uuid` | `UUID` | External-facing |
| `use_case` | `Text NOT NULL UNIQUE` | `workflow_generation`, `rule_tuning_analysis` |
| `display_name` | `Text NOT NULL` | "Workflow Code Generation", "Detection Rule Tuning Analysis" |
| `description` | `Text` | Explains what this prompt does and when it's used |
| `system_prompt` | `Text NOT NULL` | The editable system prompt text |
| `available_variables` | `JSONB NOT NULL` | Documents template variables: `[{"name": "description", "type": "string", "description": "User's workflow description"}, ...]` |
| `is_system` | `Boolean NOT NULL DEFAULT true` | System-seeded prompts |
| `version` | `Integer NOT NULL DEFAULT 1` | Incremented on every edit |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | |

**Seed data (`app/seed/llm_prompts.py`):**

Two prompts seeded at startup:

1. **`workflow_generation`** — Extract the current `_SYSTEM_PROMPT` from `app/services/workflow_generator.py` (lines 27-166) as the default value. `available_variables`: `description`, `workflow_type`, `indicator_types`.

2. **`rule_tuning_analysis`** — New prompt (see Wave D for content). `available_variables`: `rule_name`, `rule_documentation`, `metrics_summary`, `sample_alerts`, `sample_fp_alerts`, `top_indicators`.

Seeding is idempotent (skip if `use_case` already exists) — same pattern as `app/seed/enrichment_providers.py`.

**Acceptance criteria:**
- [ ] Migration creates table
- [ ] Two prompts seeded at startup
- [ ] Seed is idempotent

---

### Chunk C.2 — Repository + Schemas + API Routes

**Files to create/modify:**
- `app/repositories/llm_prompt_repository.py` (new)
- `app/schemas/llm_prompts.py` (new)
- `app/api/v1/llm_prompts.py` (new)
- `app/api/v1/__init__.py` (register router)

**Repository:**
```python
class LLMPromptRepository:
    async def get_by_uuid(self, uuid: UUID) -> LLMPrompt | None: ...
    async def get_by_use_case(self, use_case: str) -> LLMPrompt | None: ...
    async def list(self) -> list[LLMPrompt]: ...
    async def patch(self, prompt: LLMPrompt, updates: dict) -> LLMPrompt: ...
    async def reset_to_default(self, prompt: LLMPrompt) -> LLMPrompt: ...
```

Note: No `create` or `delete` — prompts are system-seeded only. Users can only edit and reset.

**Endpoints:**

| Method | Path | Auth Scope | Description |
|--------|------|-----------|-------------|
| `GET` | `/v1/llm-prompts` | `admin` | List all prompts |
| `GET` | `/v1/llm-prompts/{uuid}` | `admin` | Get single prompt |
| `PATCH` | `/v1/llm-prompts/{uuid}` | `admin` | Edit prompt (system_prompt field only) |
| `POST` | `/v1/llm-prompts/{uuid}/reset` | `admin` | Reset to seeded default |

**Patch behavior:**
- Only `system_prompt` is editable
- On patch: increment `version`, update `updated_at`
- `is_system` is not user-editable

**Reset behavior:**
- Look up the default from `app/seed/llm_prompts.py` by `use_case`
- Replace `system_prompt` with default value
- Increment `version`

**Acceptance criteria:**
- [ ] List returns both seeded prompts
- [ ] Patch updates system_prompt and increments version
- [ ] Reset restores original seeded content
- [ ] No create/delete endpoints

---

### Chunk C.3 — Frontend: Prompt Management UI

**Files to create/modify:**
- `ui/src/pages/settings/llm-prompts/index.tsx` (new)
- `ui/src/hooks/use-api.ts` (add hooks)
- `ui/src/lib/types.ts` (add types)
- `ui/src/router.tsx` (add route)

**Navigation:**
- Add "AI Prompts" under Settings section in sidebar (icon: `MessageSquareCode` from lucide)
- Route: `/settings/ai-prompts`
- Place it directly below "AI Providers" in the sidebar

**Page structure:**
- List both prompts as cards (not a table — these are long-form text)
- Each card shows:
  - Display name + use case badge
  - Description
  - "Last modified" timestamp + version number
  - "Edit" button → opens editor
  - "Reset to Default" button (with confirmation dialog)

**Editor view (inline, not a separate page):**
- Expanding card or full-page editor (use `DocumentationEditor` pattern with Write/Preview tabs)
- Left side: `Textarea` or CodeMirror for the system prompt (monospace, large)
- Right sidebar: "Available Variables" panel listing each variable with its type and description (read from `available_variables` JSONB)
- Variables displayed as: `{{variable_name}}` — type — description
- Save button, Cancel button
- Character count / word count indicator

**Implementation notes:**
- React Query hooks: `useLLMPrompts()`, `useLLMPrompt(uuid)`, `usePatchLLMPrompt()`, `useResetLLMPrompt(uuid)`
- Use same card styling as the rest of settings pages
- The prompt text can be very long (the workflow generation prompt is ~140 lines). The textarea should be large with line numbers if feasible (CodeMirror in plain text mode)

**Acceptance criteria:**
- [ ] Both prompts displayed
- [ ] Edit workflow updates prompt and shows new version
- [ ] Reset to default works with confirmation
- [ ] Available variables panel is informative
- [ ] Large prompts are comfortable to edit (scrollable, monospace)

---

## Wave D — AI-Assisted Detection Rule Tuning

### Purpose
Use an LLM to analyze a detection rule's historical alert data and provide tuning recommendations to reduce false positives.

**Depends on:** Wave A (metrics data) + Wave C (prompt management)

---

### Chunk D.1 — Backend: Rule Tuning Analysis Service

**Files to create/modify:**
- `app/services/rule_tuning.py` (new)
- `app/schemas/rule_tuning.py` (new)
- `app/api/v1/detection_rules.py` (add endpoint)

**New service function:**
```python
async def analyze_detection_rule(
    db: AsyncSession,
    detection_rule_id: int,
    detection_rule_uuid: UUID,
) -> RuleTuningAnalysisResponse:
```

**What it does:**

1. **Gather context (deterministic):**
   - Fetch detection rule (name, documentation, severity, MITRE info)
   - Call `compute_detection_rule_metrics()` from Wave A for last 90 days
   - Fetch 10 most recent alerts for this rule (normalized fields only, no raw_payload) — for pattern analysis
   - Fetch up to 10 alerts closed as False Positive (title, severity, close_classification, indicators) — for FP pattern analysis
   - Fetch top indicators associated with this rule's alerts

2. **Build prompt (deterministic):**
   - Load system prompt from DB via `LLMPromptRepository.get_by_use_case("rule_tuning_analysis")`
   - Build user prompt by filling template variables with gathered data
   - Format alert samples as structured JSON for token efficiency

3. **Call LLM (via `call_llm()` from `app/services/llm_client.py`):**
   - Resolve provider via `LLMProviderRepository.get_active_for_use_case("rule_tuning")`
   - If no provider: return 503 "No LLM provider configured for rule tuning"

4. **Parse response:**
   - LLM returns structured JSON with:
     ```json
     {
       "summary": "Overall assessment of rule health",
       "false_positive_patterns": [
         {"pattern": "...", "frequency": "high|medium|low", "suggestion": "..."}
       ],
       "tuning_recommendations": [
         {"title": "...", "description": "...", "impact": "high|medium|low", "effort": "low|medium|high"}
       ],
       "severity_assessment": "Current severity seems appropriate / Consider adjusting to...",
       "confidence": "high|medium|low"
     }
     ```

**Default system prompt for `rule_tuning_analysis`** (seeded in C.1):
```
You are an expert SOC analyst and detection engineer. You analyze detection rules
and their historical alert data to identify false positive patterns and provide
actionable tuning recommendations.

You are given:
- The detection rule's documentation and metadata
- Effectiveness metrics (FP rate, TP rate, alert volume, response times)
- Sample recent alerts (to understand what this rule triggers on)
- Sample false positive alerts (to understand FP patterns)
- Top indicators associated with this rule

Your analysis must be:
1. Data-driven — cite specific numbers from the metrics
2. Actionable — each recommendation should be implementable
3. Prioritized — rank by impact and effort
4. Honest — if the rule looks healthy, say so

Respond in JSON only (no markdown fences):
{
  "summary": "...",
  "false_positive_patterns": [...],
  "tuning_recommendations": [...],
  "severity_assessment": "...",
  "confidence": "high|medium|low"
}
```

**API endpoint:**
```
POST /v1/detection-rules/{uuid}/analyze
```
- Auth scope: `admin` (consumes LLM tokens)
- Rate limited: more restrictive (e.g., 5/minute) since it's expensive
- Returns `DataResponse[RuleTuningAnalysisResponse]`
- 503 if no LLM provider configured

**Response schema:**
```python
class FalsePositivePattern(BaseModel):
    pattern: str
    frequency: str  # high, medium, low
    suggestion: str

class TuningRecommendation(BaseModel):
    title: str
    description: str
    impact: str  # high, medium, low
    effort: str  # low, medium, high

class RuleTuningAnalysisResponse(BaseModel):
    detection_rule_uuid: UUID
    summary: str
    false_positive_patterns: list[FalsePositivePattern]
    tuning_recommendations: list[TuningRecommendation]
    severity_assessment: str
    confidence: str
    analyzed_at: datetime
    llm_provider: str  # display_name of provider used
    prompt_version: int  # version of the prompt used
```

**Acceptance criteria:**
- [ ] Endpoint gathers correct context data
- [ ] Prompt is loaded from DB (editable)
- [ ] LLM call routes through `call_llm()` (multi-provider)
- [ ] Response is properly parsed and validated
- [ ] 503 when no LLM provider configured
- [ ] Rate limited more restrictively than standard endpoints

---

### Chunk D.2 — Frontend: Rule Tuning Analysis UI

**Files to create/modify:**
- `ui/src/pages/settings/detection-rules/detail.tsx` (add "AI Analysis" tab or section)
- `ui/src/pages/settings/detection-rules/analysis-tab.tsx` (new)
- `ui/src/hooks/use-api.ts` (add hooks)
- `ui/src/lib/types.ts` (add types)

**What to build:**

Add an "AI Analysis" tab on the detection rule detail page (third tab after Documentation and Metrics).

**Tab content:**
- Top: "Analyze Rule" button with sparkle icon + explanatory text: "Use AI to analyze this rule's alert patterns and get tuning recommendations"
- If no LLM provider configured: show info banner linking to `/settings/ai-providers`
- Loading state: skeleton with "Analyzing rule..." message
- Results display:
  - **Summary card** — the `summary` text with confidence badge
  - **False Positive Patterns** — card list, each with pattern description, frequency badge (color-coded), suggestion
  - **Tuning Recommendations** — card list, each with title, description, impact badge, effort badge
  - **Severity Assessment** — single card
  - **Metadata footer** — "Analyzed at {time} using {provider} (prompt v{version})"
- "Re-analyze" button to run again

**Badge colors:**
- Impact/frequency high = red, medium = amber, low = green
- Effort low = green, medium = amber, high = red
- Confidence high = teal, medium = amber, low = red

**Implementation notes:**
- Use `useMutation` for the analyze call (it's a POST, not a query)
- Store the last analysis result in component state (not persisted — re-analyze is cheap enough)
- If we want persistence: could store in a `rule_analyses` table, but for v1.1 keeping it ephemeral is simpler
- The analysis typically takes 5-15 seconds — show a progress indicator

**Acceptance criteria:**
- [ ] "AI Analysis" tab renders correctly
- [ ] Analyze button triggers analysis and shows loading state
- [ ] Results render with proper formatting and badges
- [ ] Info banner shown when no LLM provider configured
- [ ] Re-analyze button works

---

## Wave E — Enhanced Workflow Authoring

### Purpose
Improve the existing workflow generation UX with DB-driven prompts and iterative refinement.

**Depends on:** Wave C (prompt management) + Wave B.5 (multi-provider client)

---

### Chunk E.1 — Backend: Migrate Workflow Generator to DB Prompts

**Files to modify:**
- `app/services/workflow_generator.py`
- `app/api/v1/workflows.py`

**What to change:**

The `_SYSTEM_PROMPT` constant in `workflow_generator.py` becomes the fallback. The primary source is now the DB:

```python
async def generate_workflow_code(
    description: str,
    workflow_type: str | None,
    indicator_types: list[str],
    db: AsyncSession,  # NEW: needed to read prompt from DB
    cfg: Settings,     # Still needed for env var fallback
) -> WorkflowGenerateResponse:
    # 1. Load prompt from DB
    repo = LLMPromptRepository(db)
    prompt_row = await repo.get_by_use_case("workflow_generation")
    system_prompt = prompt_row.system_prompt if prompt_row else _SYSTEM_PROMPT  # fallback

    # 2. Resolve LLM provider
    provider_repo = LLMProviderRepository(db)
    provider = await provider_repo.get_active_for_use_case("workflow_generation")
    # ... fallback to ANTHROPIC_API_KEY env var ...

    # 3. Call LLM
    response_text = await call_llm(provider_or_fallback, system_prompt, user_prompt)
    # ... parse and validate as before ...
```

**Acceptance criteria:**
- [ ] Prompt loaded from DB when available, falls back to hardcoded
- [ ] Provider loaded from DB when available, falls back to env var
- [ ] All existing workflow generation tests still pass

---

### Chunk E.2 — Frontend: Iterative Workflow Generation UX

**Files to modify:**
- `ui/src/pages/workflows/detail.tsx`
- `ui/src/components/workflow-code-editor.tsx`
- `ui/src/hooks/use-api.ts` (if needed)

**What to build:**

Enhance the existing workflow code editor with iterative AI refinement:

1. **"Generate with AI" button** (already exists as the generate flow) — no change to trigger
2. **After initial generation, add a refinement input:**
   - Text input below the code editor: "Refine: e.g., 'add pagination handling', 'add retry logic'"
   - "Refine" button sends a new generation request with:
     - The current code as context (appended to user prompt)
     - The refinement instruction
   - This is a new endpoint or an extension of the existing generate endpoint

3. **New endpoint or extended request:**
```
POST /v1/workflows/generate
{
  "description": "...",
  "workflow_type": "...",
  "indicator_types": [...],
  "existing_code": "...",         // NEW: optional, for refinement
  "refinement_instruction": "..." // NEW: optional, for refinement
}
```

When `existing_code` is provided, the user prompt changes to include:
```
Here is the existing workflow code:
```python
{existing_code}
```

The user wants the following refinement:
{refinement_instruction}

Update the code accordingly. Return the complete updated code.
```

4. **UI flow:**
   - User clicks "Generate with AI" → gets initial code
   - Code appears in editor, user can manually edit
   - Below editor: refinement text input + "Refine with AI" button
   - Each refinement replaces the editor content with the new version
   - User can undo (editor supports undo) or re-generate from scratch

**Acceptance criteria:**
- [ ] Refinement input appears after initial generation
- [ ] Refinement request includes existing code
- [ ] Generated code replaces editor content
- [ ] Multiple rounds of refinement work
- [ ] Manual edits between refinements are preserved (sent as `existing_code`)

---

## Project Management

### Dependency Graph

```
Wave A (Detection Rule Metrics + Alerts)    Wave B (LLM Provider Foundation)
  A.1 ──→ A.2                                B.1 ──→ B.2 ──→ B.3 ──→ B.4
      └──→ A.3 (no backend dep)                                │
                                                                B.5
                                                                │
                                            Wave C (Prompt Management)
                                              C.1 ──→ C.2 ──→ C.3
                                                │
                ┌───────────────────────────────┤
                ▼                               ▼
Wave D (Rule Tuning)                      Wave E (Workflow Enhancement)
  D.1 ──→ D.2                              E.1 ──→ E.2
  (needs A.1 + C.2 + B.5)                  (needs C.2 + B.5)
```

Note: A.3 only depends on A.1 for the `AlertSummary` schema change (backend). The frontend can be built in parallel with A.2 once A.1 is done.

### Parallelization Strategy

**Phase 1 (fully parallel):** A.1 + B.1 can start simultaneously (no dependencies on each other)

**Phase 2 (parallel):** A.2 + A.3 + B.2 (A.2 and A.3 both depend on A.1; B.2 depends on B.1)

**Phase 3 (parallel):** B.3 + B.4 can overlap (B.3 must finish for B.4's hooks to work, but B.4 UI can be stubbed)

**Phase 4:** B.5 + C.1 (B.5 depends on B.2; C.1 depends on B.1 for migration ordering)

**Phase 5 (parallel):** C.2 + C.3 (C.2 depends on C.1; C.3 depends on C.2 for hooks)

**Phase 6 (fully parallel):** D.1 + E.1 (both depend on C.2 + B.5, but are independent of each other)

**Phase 7 (parallel):** D.2 + E.2 (D.2 depends on D.1; E.2 depends on E.1)

### Chunk Summary

| Chunk | Name | Dependencies | Est. Complexity | Status |
|-------|------|-------------|-----------------|--------|
| A.1 | Detection Rule Metrics Service + API | None | Medium | COMPLETE |
| A.2 | Detection Rule Metrics Tab (DnD) | A.1 | High (DnD grid + charts) | COMPLETE |
| A.3 | Detection Rule Alerts Tab | A.1 (schema) | Medium | COMPLETE |
| B.1 | LLM Provider DB Model + Migration | None | Low | Pending |
| B.2 | LLM Provider Repository + Schemas | B.1 | Low | Pending |
| B.3 | LLM Provider API Routes | B.2 | Medium | Pending |
| B.4 | LLM Provider Settings Page (UI) | B.3 | Medium | Pending |
| B.5 | Migrate Workflow Generator to Multi-Provider | B.2 | Medium | Pending |
| C.1 | Prompt DB Model + Migration + Seed | B.1 (migration ordering) | Low | Pending |
| C.2 | Prompt Repository + Schemas + API | C.1 | Low | Pending |
| C.3 | Prompt Management UI | C.2 | Medium | Pending |
| D.1 | Rule Tuning Analysis Service | A.1, C.2, B.5 | High | Pending |
| D.2 | Rule Tuning Analysis UI | D.1 | Medium | Pending |
| E.1 | Workflow Generator → DB Prompts | C.2, B.5 | Low | Pending |
| E.2 | Iterative Workflow Generation UX | E.1 | Medium | Pending |

**Total: 15 chunks across 5 waves**

### Acceptance Criteria (Cross-Cutting)

- [ ] All new backend code passes `ruff` linting
- [ ] All new backend code passes `mypy` type checking
- [ ] All new endpoints have appropriate rate limiting
- [ ] All new endpoints enforce auth scopes
- [ ] All migrations are reversible
- [ ] No LLM tokens consumed in the deterministic pipeline
- [ ] Platform works fully without any LLM provider configured
- [ ] Existing tests remain green
- [ ] New API endpoints follow existing response envelope patterns (`DataResponse[T]`, `PaginatedResponse[T]`)

---

## Verification Plan

### End-to-End Test Flow

1. **No LLM configured:** Verify platform works normally. Metrics tab shows data. AI Analysis tab shows "configure provider" banner. Workflow generate falls back to env var or returns 503.

2. **Configure Anthropic provider:**
   - Go to Settings → AI Providers → Add Provider
   - Select Anthropic, enter API key, assign to both use cases
   - Test Connection → verify success

3. **Detection Rule Metrics:**
   - Navigate to any detection rule with alerts
   - Click Metrics tab → verify all cards render
   - Drag cards around → refresh page → verify layout persisted
   - Reset Layout → verify defaults restored

4. **Rule Tuning Analysis:**
   - On same detection rule, click AI Analysis tab
   - Click "Analyze Rule" → wait for results
   - Verify summary, FP patterns, recommendations render
   - Verify metadata footer shows correct provider + prompt version

5. **Edit Prompt:**
   - Go to Settings → AI Prompts
   - Edit the rule tuning prompt (add "Also suggest MITRE ATT&CK coverage gaps")
   - Re-run analysis → verify new instruction is reflected in output
   - Reset to default → verify original prompt restored

6. **Workflow Generation:**
   - Create new workflow → Generate with AI
   - Verify it uses the DB-configured provider
   - Use refinement: "add retry logic for 429 responses"
   - Verify code is updated
   - Switch LLM provider to OpenAI → verify generation still works

7. **Multi-provider:**
   - Configure OpenAI provider for workflow_generation
   - Configure Anthropic for rule_tuning
   - Verify each use case routes to the correct provider
