# Calseta UI — Engineering Context

Companion to `DESIGN_SYSTEM.md`. Read both before building any new page. This file covers the implementation layer: tech stack, file conventions, routing, API client, types, and React Query patterns.

---

## Tech Stack

| Layer | Library | Notes |
|-------|---------|-------|
| Framework | React 18 + Vite | |
| Routing | TanStack Router v1 | File-based route objects in `src/router.tsx` |
| Server state | TanStack Query v5 | All hooks in `src/hooks/use-api.ts` |
| UI primitives | shadcn/ui | Customized; source in `src/components/ui/` |
| Styling | Tailwind CSS v3 | Design tokens in `src/index.css` |
| Icons | lucide-react | Full icon map in `DESIGN_SYSTEM.md` |
| Toasts | sonner | Only `toast.success()` / `toast.error()` |
| Dates | date-fns | `relativeTime()` and `formatDate()` from `src/lib/format.ts` |
| Charts | recharts | Dashboard only |
| Drag grid | react-grid-layout | Dashboard only |

---

## File Organization

```
ui/src/
  App.tsx                       Entry point — QueryClientProvider + AuthProvider + RouterProvider
  router.tsx                    All routes registered here; one file, no splitting
  index.css                     CSS custom properties (color tokens, fonts)
  components/
    ui/                         shadcn primitives (never import from shadcn directly — use these)
    layout/                     AppLayout, Sidebar, TopBar
    detail-page/                DetailPageHeader, DetailPageLayout, etc. — use for every detail page
    {feature}/                  Feature-specific shared components
  hooks/
    use-api.ts                  ALL React Query hooks — queries and mutations
    use-table-state.ts          Pagination + sort + filters
    use-page-size.ts            Persisted page size (localStorage)
    use-resizable-columns.ts    Column width persistence (localStorage)
  lib/
    api-client.ts               Thin fetch wrapper (`api.get/post/patch/delete/upload`)
    types.ts                    ALL TypeScript types for API responses
    format.ts                   Formatters: formatDate, relativeTime, severityColor, statusColor, etc.
    auth.tsx                    AuthContext + useAuth hook
    utils.ts                    `cn()` helper
  pages/
    dashboard/index.tsx
    alerts/index.tsx + detail.tsx
    workflows/index.tsx + detail.tsx + approvals.tsx
    settings/
      agents/index.tsx + detail.tsx
      api-keys/index.tsx + detail.tsx
      context-docs/index.tsx + detail.tsx
      detection-rules/index.tsx + detail.tsx + metrics-tab.tsx
      enrichment-providers/index.tsx + detail.tsx
      indicator-mappings.tsx
      sources.tsx
    login.tsx
```

---

## Adding a New Page — Checklist

### 1. Create the page file(s)

```
ui/src/pages/{section}/{entity}/index.tsx     # list page
ui/src/pages/{section}/{entity}/detail.tsx    # detail page
```

Name exports: `{Entity}ListPage` and `{Entity}DetailPage`.

### 2. Register routes in `src/router.tsx`

```tsx
import { {Entity}ListPage } from "@/pages/{section}/{entity}";
import { {Entity}DetailPage } from "@/pages/{section}/{entity}/detail";

const {entity}Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/{section}/{entity-plural}",
  component: {Entity}ListPage,
});

const {entity}DetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/{section}/{entity-plural}/$uuid",
  component: {Entity}DetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "default-tab",
  }),
});

// Add both to routeTree.addChildren([...])
```

Route namespaces in use:
- `/` — dashboard
- `/alerts`, `/workflows`, `/approvals` — core ops
- `/manage/*` — agents, enrichment-providers, detection-rules, context-docs
- `/settings/*` — api-keys, alert-sources, indicator-mappings

New agent control plane features should use `/agents/*` (top-level) or extend `/manage/*`.

### 3. Add sidebar entry in `src/components/layout/sidebar.tsx`

Three nav arrays — add to the correct one:
- `mainNav` — primary ops (Dashboard, Alerts, Workflows, Approvals)
- `manageNav` — platform config (Agents, Enrichments, Detection Rules, Context Docs)
- `settingsNav` — system settings (API Keys, Alert Sources, Indicator Mappings)

```tsx
{ to: "/manage/llm-providers", icon: BrainCircuit, label: "LLM Providers" },
```

### 4. Add TypeScript types in `src/lib/types.ts`

Add response interfaces to this file. No inline type definitions in pages or hooks.

```ts
export interface LlmProvider {
  uuid: string;
  name: string;
  provider_type: string;
  is_active: boolean;
  // ...
  created_at: string;
  updated_at: string;
}
```

### 5. Add React Query hooks in `src/hooks/use-api.ts`

All queries and mutations live here. Import from `@/lib/types`.

```ts
// Query
export function useLlmProviders(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["llm-providers", qs],
    queryFn: () => api.get<PaginatedResponse<LlmProvider>>(`/llm-providers${qs ? `?${qs}` : ""}`),
  });
}

export function useLlmProvider(uuid: string) {
  return useQuery({
    queryKey: ["llm-provider", uuid],
    queryFn: () => api.get<DataResponse<LlmProvider>>(`/llm-providers/${uuid}`),
    enabled: !!uuid,
  });
}

// Mutation
export function useCreateLlmProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateLlmProviderBody) =>
      api.post<DataResponse<LlmProvider>>("/llm-providers", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-providers"] }),
  });
}

export function usePatchLlmProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Partial<LlmProvider> }) =>
      api.patch<DataResponse<LlmProvider>>(`/llm-providers/${uuid}`, body),
    onSuccess: (_, { uuid }) => {
      qc.invalidateQueries({ queryKey: ["llm-providers"] });
      qc.invalidateQueries({ queryKey: ["llm-provider", uuid] });
    },
  });
}

export function useDeleteLlmProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/llm-providers/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-providers"] }),
  });
}
```

---

## API Client

`src/lib/api-client.ts` — thin fetch wrapper with `Authorization: Bearer {api_key}` injected from localStorage.

```ts
import { api } from "@/lib/api-client";

api.get<T>(path)                    // GET
api.post<T>(path, body?)            // POST JSON
api.patch<T>(path, body)            // PATCH JSON
api.delete<T>(path)                 // DELETE
api.upload<T>(path, formData)       // POST multipart
```

On 401/403, clears API key and reloads — handled automatically.

---

## Response Envelopes

All API responses unwrap from:

```ts
// Single entity
{ data: T, meta: Record<string, unknown> }

// Paginated list
{ data: T[], meta: { total: number, page: number, page_size: number, total_pages: number } }
```

In pages:
```ts
const { data, isLoading, refetch, isFetching } = useLlmProviders(params);
const providers = data?.data ?? [];
const meta = data?.meta;
```

---

## Table State Pattern

```tsx
const {
  page, setPage,
  pageSize, handlePageSizeChange,
  sort, updateSort,
  filters, updateFilter,
  clearAll,
  hasActiveFilters,
  params,           // ← pass directly to useXxx(params)
} = useTableState({
  status: [],        // ← initial filter shapes
  provider_type: [],
});
```

`params` is a `Record<string, string | number | boolean | undefined>` ready for the API hook.

---

## Utility Functions (`src/lib/format.ts`)

| Function | Returns |
|----------|---------|
| `formatDate(iso)` | `"Apr 3, 2026 14:32 UTC"` |
| `relativeTime(iso)` | `"2 hours ago"` |
| `formatSeconds(n)` | `"42s"` / `"3m"` / `"1.5h"` / `"2.1d"` |
| `formatPercent(rate)` | `"87.3%"` (rate = 0–1) |
| `severityColor(s)` | Tailwind badge class string |
| `statusColor(s)` | Tailwind badge class string |
| `enrichmentStatusColor(s)` | Tailwind badge class string |
| `maliceColor(s)` | Tailwind badge class string |
| `riskColor(s)` | Tailwind badge class string |
| `eventDotColor(eventType)` | `bg-{color}` class for activity timeline dots |

---

## Current Page Inventory

| Page | Route | Export |
|------|-------|--------|
| Dashboard | `/` | `DashboardPage` |
| Alerts list | `/alerts` | `AlertsListPage` |
| Alert detail | `/alerts/$uuid` | `AlertDetailPage` |
| Workflows list | `/workflows` | `WorkflowsListPage` |
| Workflow detail | `/workflows/$uuid` | `WorkflowDetailPage` |
| Approvals | `/approvals` | `ApprovalsPage` |
| Detection Rules list | `/manage/detection-rules` | `DetectionRulesPage` |
| Detection Rule detail | `/manage/detection-rules/$uuid` | `DetectionRuleDetailPage` |
| Context Docs list | `/manage/context-docs` | `ContextDocsPage` |
| Context Doc detail | `/manage/context-docs/$uuid` | `ContextDocDetailPage` |
| Agents list | `/manage/agents` | `AgentsPage` |
| Agent detail | `/manage/agents/$uuid` | `AgentDetailPage` |
| Enrichment Providers list | `/manage/enrichment-providers` | `EnrichmentProvidersPage` |
| Enrichment Provider detail | `/manage/enrichment-providers/$uuid` | `EnrichmentProviderDetailPage` |
| API Keys list | `/settings/api-keys` | `ApiKeysPage` |
| API Key detail | `/settings/api-keys/$uuid` | `ApiKeyDetailPage` |
| Alert Sources | `/settings/alert-sources` | `SourcesPage` |
| Indicator Mappings | `/settings/indicator-mappings` | `IndicatorMappingsPage` |
| Login | — | `LoginPage` |

---

## Existing Types Reference

Types defined in `src/lib/types.ts`:

- **Envelopes**: `DataResponse<T>`, `PaginatedResponse<T>`
- **Alerts**: `AlertSummary`, `AlertResponse`, `AlertStatus`, `AlertSeverity`, `EnrichedIndicator`, `AgentFinding`
- **Indicators**: `IndicatorDetailResponse`, `IndicatorType`, `INDICATOR_TYPES`, `MaliceLevel`
- **Workflows**: `WorkflowSummary`, `WorkflowResponse`, `WorkflowRun`, `WorkflowApproval`
- **Detection Rules**: `DetectionRule`, `DetectionRuleMetrics`
- **Context Docs**: `ContextDocument`
- **Agents**: `AgentRegistration`
- **Enrichment**: `EnrichmentProvider`, `EnrichmentFieldExtraction`, `EnrichmentProviderTestResult`
- **Indicator Mappings**: `IndicatorFieldMapping`, `TestExtractionResult`
- **API Keys**: `ApiKeyResponse`, `ApiKeyCreateResponse`
- **Source Integrations**: `SourceIntegration`
- **Metrics**: `MetricsSummary`, `QueueMetrics`, `QueueEntry`
- **Health**: `HealthResponse`
- **Settings**: `ApprovalDefaults`
- **Graph**: `AlertRelationshipGraph`, `GraphAlertNode`, `GraphIndicatorNode`

---

## New Types Needed for Agent Control Plane (v2)

When implementing agent control plane pages, add these to `types.ts` as API schemas are finalized:

- `LlmProvider` — provider_type, model, base_url, has_credentials, is_active, budget_config
- `SecretRef` — name, provider_type (local_encrypted / env_var), description, last_rotated_at
- `AgentRunner` — orchestrator config, assigned LLM, tool permissions, budget, schedule
- `AgentRun` — run history with token usage, cost, duration, status, error
- `AgentTool` — registered tools available to agent runners
- `PlatformMetrics` — token usage, cost, run counts, error rates (extends `MetricsSummary`)

---

## Auth Context

```tsx
import { useAuth } from "@/lib/auth";

const { isAuthenticated, logout } = useAuth();
```

API key stored in `localStorage` as `calseta_api_key`. Auth is purely header-based — no sessions, no cookies.

---

## Design System Reference

See `DESIGN_SYSTEM.md` for:
- Full color token reference
- Typography scale
- Badge patterns
- Icon assignments
- List page and detail page layout patterns
- Form patterns (create dialog, edit modal, chip inputs, toggle groups)
- Spacing standards
- Interaction states
- Toast conventions
