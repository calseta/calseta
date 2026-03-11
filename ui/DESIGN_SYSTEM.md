# Calseta UI — Design System

Reference for building consistent, high-quality interfaces. Read this before creating or modifying any page.

---

## Color Tokens

All colors are CSS custom properties in `src/index.css`. Use Tailwind classes, never raw hex values.

### Brand Palette

| Token | Hex | Tailwind Class | Use For |
|-------|-----|----------------|---------|
| `teal` | `#4D7D71` | `text-teal`, `bg-teal` | Primary actions, active states, links |
| `teal-light` | `#7FCAB8` | `text-teal-light` | Hover emphasis, active tab text, link text |
| `teal-dim` | `#3a5f56` | `bg-teal-dim` | Button hover (`hover:bg-teal-dim`) |
| `amber` | `#FFBB1A` | `text-amber`, `bg-amber/10` | Warnings, "global" scope, triaging status |
| `red-threat` | `#EA591B` | `text-red-threat` | Destructive actions, critical severity, open alerts |

### Surface & Text

| Token | Hex | Use For |
|-------|-----|---------|
| `background` | `#080b0f` | Page background |
| `surface` | `#0d1117` | Input backgrounds, card-level surfaces |
| `surface-hover` | `#111820` | Hovered card surfaces |
| `surface-raised` | `#161b22` | Elevated panels |
| `card` | `#0d1117` | Card backgrounds |
| `foreground` | `#CCD0CF` | Primary text |
| `dim` | `#57635F` | Muted text, secondary labels, inactive states |
| `muted-foreground` | `#57635F` | Form labels, field labels |
| `text-muted` | `#2a3530` | Lowest contrast text |
| `border` | `#1e2a25` | All borders — cards, inputs, tables, dividers |

### Status Colors by Context

**Alert Status:**
| Status | Color | Badge Classes |
|--------|-------|---------------|
| Open | `red-threat` | `text-red-threat bg-red-threat/10 border-red-threat/30` |
| Triaging | `amber` | `text-amber bg-amber/10 border-amber/30` |
| Escalated | `teal` | `text-teal bg-teal/10 border-teal/30` |
| Closed | `dim` | `text-dim bg-dim/10 border-dim/30` |

**Severity:**
| Level | Color |
|-------|-------|
| Critical | `red-threat` |
| High | `amber` |
| Medium | `teal` |
| Low | `dim` |
| Informational | `text-muted` |
| Pending | `border` |

**Active/Inactive:**
| State | Badge Classes |
|-------|---------------|
| Active | `text-teal bg-teal/10 border-teal/30` |
| Inactive/Revoked | `text-dim bg-dim/10 border-dim/30` |

**Malice Verdict:**
| Verdict | Color |
|---------|-------|
| Malicious | `red-threat` |
| Suspicious | `amber` |
| Benign | `teal` |
| Pending | `dim` |

---

## Typography

Two fonts, always dark theme.

| Element | Font | Weight | Classes |
|---------|------|--------|---------|
| Headings (h1-h6) | Manrope | 800 | `font-heading font-extrabold tracking-tight` |
| Body / Code | IBM Plex Mono | 400-500 | `font-sans` (default) |
| Page title | Manrope | 800 | `text-xl font-heading font-extrabold tracking-tight` |
| Section title | IBM Plex Mono | 500 | `text-sm font-medium text-muted-foreground` |
| Sidebar section label | — | 500 | `text-[11px] font-medium uppercase tracking-wider text-dim` |
| Status card label | — | 500 | `text-[11px] font-medium uppercase tracking-wider text-dim` |
| Status card value | — | 500 | `text-sm font-medium text-foreground` |
| Field label | — | 400 | `text-xs text-muted-foreground` |
| Field value | — | 400 | `text-xs text-foreground` |
| Table header | — | 400 | `text-dim text-xs` |
| Table cell (default) | — | 400 | `text-sm text-foreground` |
| Table cell (muted) | — | 400 | `text-xs text-dim` |
| Badge text | — | 500 | `text-[11px]` |
| Inline code | — | 400 | `text-[10px] font-mono text-dim bg-surface px-1.5 py-0.5 rounded border border-border` |

---

## Badge Pattern

Always `variant="outline"` with semantic color classes:

```tsx
<Badge variant="outline" className="text-[11px] text-{color} bg-{color}/10 border-{color}/30">
  {label}
</Badge>
```

For badges with icons, add `gap-1` and a `h-2.5 w-2.5` icon before the text.

Neutral/plain badges: `text-foreground border-border` or `text-dim border-border`.

---

## Icons (lucide-react)

Consistent icon assignments — do not mix.

### Domain Icons
| Concept | Icon | Notes |
|---------|------|-------|
| Alerts | `ShieldAlert` | Sidebar, headers |
| Workflows | `Workflow` | — |
| Approvals | `CheckCircle2` | — |
| Agents | `Bot` | — |
| Detection Rules | `Radar` | — |
| Context Docs | `BookOpen` | — |
| Enrichment | `Microscope` | — |
| API Keys | `Key` | — |
| Indicator Mappings | `MapPin` | — |
| Sources | `FileCode2` | — |
| Dashboard | `LayoutDashboard` | — |

### Action Icons
| Action | Icon |
|--------|------|
| Create/Add | `Plus` |
| Edit | `Pencil` |
| Save | `Save` |
| Cancel | `X` |
| Delete | `Trash2` |
| Copy | `Copy` → `Check` (after copy) |
| Refresh | `RefreshCw` (add `animate-spin` when fetching) |
| Back | `ArrowLeft` |
| Execute/Send | `Send` |
| Revoke | `Ban` |

### Tab Icons
| Tab Type | Icon | Size |
|----------|------|------|
| Documentation / Content | `FileText` | `h-3.5 w-3.5 mr-1` |
| Targeting Rules | `Target` | `h-3.5 w-3.5 mr-1` |
| Configuration | `Settings` | `h-3.5 w-3.5 mr-1` |
| Activity | `Clock` | `h-3.5 w-3.5 mr-1` |
| Indicators | `Search` | `h-3.5 w-3.5 mr-1` |
| Raw JSON / Code | `Code2` | `h-3.5 w-3.5 mr-1` |

### Metric Icons
| Metric | Icon |
|--------|------|
| MTTD (detection) | `Clock` |
| MTTA (acknowledgment) | `Timer` |
| MTTT (triage) | `Hourglass` |

### Actor Icons (activity feed)
| Actor | Icon |
|-------|------|
| System | `Cpu` |
| API | `KeyRound` |
| MCP | `Plug` |

---

## Page Patterns

### List Page

Every list page follows this structure:

```
AppLayout (title="Entity Name")
  div.space-y-4
    ├── Header Row (flex justify-between items-center)
    │   ├── Left: Refresh button + count label
    │   └── Right: Create dialog trigger button
    ├── Table (rounded-lg border border-border bg-card)
    │   ├── ResizableTable (storageKey="entity-name", columns={COLUMNS})
    │   ├── Loading: 3 skeleton rows
    │   ├── Data: rows with hover:bg-accent/50
    │   └── Empty: "No items" (text-center text-sm text-dim py-12)
    └── TablePagination (if meta exists)
```

**Header conventions:**
- Refresh: `variant="ghost" size="sm" className="h-8 w-8 p-0 text-dim hover:text-teal"`
- Count: `text-xs text-dim` — e.g., "42 alerts"
- Create button: `size="sm" className="bg-teal text-white hover:bg-teal-dim"` with `Plus` icon

**Table conventions:**
- Column definitions: `ColumnDef[]` with `key`, `initialWidth`, `minWidth`, optional `maxWidth`
- Row links: `text-teal-light hover:underline` via TanStack `<Link>`
- Action column: fixed 44px width, ghost icon buttons

### Detail Page

Every detail page follows this structure:

```
AppLayout (title="Entity Name")
  div.space-y-6
    ├── DetailPageHeader
    │   ├── backTo="/path/to/list"
    │   ├── title={entity.name}
    │   ├── badges (status, type, etc.)
    │   ├── subtitle (optional description)
    │   └── onRefresh + isRefreshing
    ├── DetailPageStatusCards
    │   └── items: 2-4 cards with icon, label, value
    │       (interactive dropdowns for editable fields like status/severity)
    └── DetailPageLayout (sidebar={...})
        ├── Main: Tabs with content
        │   ├── TabsList: bg-surface border border-border
        │   ├── TabsTrigger: data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light
        │   └── TabsContent: mt-4, Cards with section content
        └── Sidebar: DetailPageSidebar
            └── SidebarSection(s) with DetailPageField(s)
```

**Tab state** is always persisted in the URL via TanStack Router's `validateSearch`:
```tsx
validateSearch: (search: Record<string, unknown>) => ({
  tab: (search.tab as string) || "default-tab",
})
```

**Sidebar conventions:**
- "Details" section always first: UUID (CopyableText), status, type, dates (formatDate)
- Additional sections as needed: "MITRE ATT&CK", "Tags", "Triggers", etc.
- Tags rendered as flex-wrap gap-1 badges

### Dashboard Page

```
AppLayout (title="Dashboard")
  SortableGrid (react-grid-layout)
    └── Cards with drag-handle, each containing a metric/chart
```

---

## Component Inventory

### Shared Components (`src/components/`)

| Component | File | Purpose |
|-----------|------|---------|
| `DetailPageHeader` | `detail-page/` | Back arrow + title + badges + refresh + actions |
| `DetailPageStatusCards` | `detail-page/` | Grid of icon + label + value status cards |
| `DetailPageLayout` | `detail-page/` | Two-column (main + sidebar) responsive layout |
| `DetailPageSidebar` | `detail-page/` | Card wrapper for sidebar content |
| `SidebarSection` | `detail-page/` | Titled section within sidebar |
| `DetailPageField` | `detail-page/` | Label-value row in sidebar |
| `DocumentationEditor` | `detail-page/` | Markdown Write/Preview with Save/Cancel |
| `TablePagination` | `table-pagination.tsx` | Page nav + rows-per-page selector |
| `SortableColumnHeader` | `sortable-column-header.tsx` | Clickable column header with sort indicator |
| `CopyableText` | `copyable-text.tsx` | Text with hover-to-copy button |
| `MarkdownPreview` | `markdown-preview.tsx` | Styled react-markdown renderer |
| `JsonViewer` | `json-viewer.tsx` | Collapsible syntax-highlighted JSON |
| `InlineTagEditor` | `inline-tag-editor.tsx` | Chip-based tag input (Enter to add, Backspace to remove) |
| `ConfirmDialog` | `confirm-dialog.tsx` | Destructive action confirmation modal |
| `AddIndicatorsForm` | `add-indicators-form.tsx` | Multi-row type+value IOC input |
| `TargetingRuleBuilder` | `targeting-rules/` | Visual rule builder + read-only display |
| `MaliceRulesBuilder` | `malice-rules-builder/` | Visual + JSON toggle for verdict rules |
| `HttpConfigBuilder` | `http-config-builder/` | Visual + JSON toggle for HTTP request templates |
| `FieldExtractionEditor` | `field-extraction-editor.tsx` | Source path → target key mapping editor |
| `WorkflowCodeEditor` | `workflow-code-editor.tsx` | Code editor with validation feedback |
| `ActorBadge` | `activity/actor-badge.tsx` | System/API/MCP actor indicator |
| `IndicatorDetailSheet` | `indicator-detail-sheet.tsx` | Slide-out enrichment results panel |
| `RunWorkflowButton` | `run-workflow-button.tsx` | Workflow execute with confirmation |
| `RunAgentButton` | `run-agent-button.tsx` | Agent test trigger |

### Layout Components (`src/components/layout/`)

| Component | Purpose |
|-----------|---------|
| `AppLayout` | Root shell: sidebar + top bar + main content area |
| `Sidebar` | Fixed w-60 navigation with section grouping |
| `TopBar` | h-14 header with title + health indicator |

### UI Primitives (`src/components/ui/`)

shadcn/ui based. Notable customizations:

- **Button**: Extra sizes `xs`, `icon-xs`, `icon-sm`, `icon-lg`
- **Badge**: `variant="outline"` is the primary variant used; rarely use `default`
- **Tabs**: Two variants — `default` (contained) and `line` (underline)
- **ResizableTable** + **ResizableTableHead**: Column-width-persisting table wrapper

---

## Form Patterns

### Create Dialog

```tsx
<Dialog open={open} onOpenChange={setOpen}>
  <DialogTrigger asChild>
    <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
      <Plus className="h-3.5 w-3.5 mr-1" />
      Create {Entity}
    </Button>
  </DialogTrigger>
  <DialogContent className="bg-card border-border max-w-lg">
    <DialogHeader>
      <DialogTitle>Create {Entity}</DialogTitle>
    </DialogHeader>
    <div className="space-y-3">
      {/* Fields */}
      <div className="space-y-1.5">
        <Label className="text-sm text-muted-foreground">Name *</Label>
        <Input className="bg-surface border-border text-sm" />
      </div>
      {/* Submit */}
      <Button
        onClick={handleCreate}
        disabled={isPending || !isValid}
        className="w-full bg-teal text-white hover:bg-teal-dim"
      >
        Create
      </Button>
    </div>
  </DialogContent>
</Dialog>
```

### Edit Modal (Detail Pages)

Pattern from workflow/detection rule detail pages — dialog with draft state:

```tsx
const [editOpen, setEditOpen] = useState(false);
const [draft, setDraft] = useState({ /* fields */ });

function openEdit() {
  setDraft({ name: entity.name, /* ... */ });
  setEditOpen(true);
}

function handleSave() {
  patchEntity.mutate(
    { uuid, body: draft },
    {
      onSuccess: () => { toast.success("Saved"); setEditOpen(false); },
      onError: () => toast.error("Failed to save"),
    },
  );
}
```

### Chip-Based List Input

For multi-value fields (tags, MITRE tactics, data sources):

```tsx
<div className="flex flex-wrap gap-1.5">
  {items.map((item) => (
    <Badge key={item} variant="outline" className="text-xs text-foreground border-border gap-1">
      {item}
      <button onClick={() => removeItem(item)}>
        <X className="h-2.5 w-2.5 text-dim hover:text-red-threat" />
      </button>
    </Badge>
  ))}
</div>
<div className="flex gap-1.5 mt-2">
  <Input
    value={inputValue}
    onChange={(e) => setInputValue(e.target.value)}
    onKeyDown={(e) => e.key === "Enter" && addItem()}
    placeholder="Add item..."
    className="bg-surface border-border text-sm"
  />
  <Button variant="outline" size="sm" onClick={addItem}>
    <Plus className="h-3.5 w-3.5" />
  </Button>
</div>
```

### Toggle Button Group

For scope/permission selection (API key scopes, allowed sources):

```tsx
<div className="flex flex-wrap gap-2">
  {ALL_OPTIONS.map((option) => {
    const selected = selectedOptions.includes(option);
    return (
      <button
        key={option}
        type="button"
        onClick={() => toggle(option)}
        className={cn(
          "px-2.5 py-1 rounded-md text-xs border transition-colors",
          selected
            ? "bg-teal/15 border-teal/40 text-teal-light"
            : "bg-surface border-border text-dim hover:border-teal/30",
        )}
      >
        {option}
      </button>
    );
  })}
</div>
```

### Inline Edit (Status Cards)

Interactive dropdowns embedded in status cards for editable fields:

```tsx
{
  label: "Status",
  icon: ShieldAlert,
  value: (
    <Select value={entity.status} onValueChange={handleStatusChange}>
      <SelectTrigger className="h-7 w-full text-xs border ...">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="bg-card border-border">
        <SelectItem value="active">Active</SelectItem>
        <SelectItem value="inactive">Inactive</SelectItem>
      </SelectContent>
    </Select>
  ),
}
```

### Visual + JSON Toggle Builder

For complex structured data (HTTP configs, malice rules):

```tsx
const [rawMode, setRawMode] = useState(false);

// Toggle button in card header:
<Button variant="ghost" size="sm" onClick={() => setRawMode(!rawMode)}>
  <Code2 className="h-3 w-3 mr-1" />
  {rawMode ? "Visual" : "JSON"}
</Button>

// Render:
{rawMode ? (
  <Textarea value={JSON.stringify(value, null, 2)} onChange={...} rows={12} />
) : (
  <VisualBuilder value={value} onChange={onChange} />
)}
```

---

## Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useTableState` | `hooks/use-table-state.ts` | Pagination + sort + filters → query params object |
| `usePageSize` | `hooks/use-page-size.ts` | Persisted page size (localStorage) |
| `useResizableColumns` | `hooks/use-resizable-columns.ts` | Column widths (localStorage per table) |
| `useDashboardLayout` | `hooks/use-dashboard-layout.ts` | Grid layout (localStorage) |
| `useAlertTableState` | `hooks/use-alert-table-state.ts` | Alert-specific filters extending useTableState |
| `use-api.ts` | `hooks/use-api.ts` | All React Query hooks — queries and mutations |

**React Query conventions:**
- All mutations call `qc.invalidateQueries()` on success for related query keys
- Stale times: 5min for metrics, 60s for graph data, defaults for everything else
- Health check: `refetchInterval: 30000` (30s polling)

---

## Spacing & Layout

| Context | Pattern |
|---------|---------|
| Page content padding | `p-6` |
| Stacked page sections | `space-y-4` (list pages), `space-y-6` (detail pages) |
| Card internal padding | `p-4` or CardHeader/CardContent defaults |
| Form field spacing | `space-y-3` or `space-y-4` |
| Field label → input gap | `space-y-1.5` or `mt-1` |
| Inline elements | `gap-1`, `gap-1.5`, `gap-2` |
| Badge groups | `flex flex-wrap gap-1` |
| Button groups | `flex gap-1.5` |
| Detail page sidebar | `w-full lg:w-80` (responsive) |
| Status cards grid | `grid-cols-2 md:grid-cols-3` (auto based on item count) |

---

## Interaction States

| State | Pattern |
|-------|---------|
| Button hover | `hover:bg-teal-dim` (primary), standard variant hovers |
| Card hover | `hover:border-teal/20 transition-colors` |
| Link hover | `hover:text-teal transition-colors` or `hover:underline` |
| Icon button hover | `text-dim hover:text-teal` or `text-dim hover:text-red-threat` (destructive) |
| Table row hover | `hover:bg-accent/50` |
| Disabled | `disabled:pointer-events-none disabled:opacity-50` |
| Loading spinner | `animate-spin` on `RefreshCw` icon |
| Loading content | `Skeleton` components matching content shape |
| Loading button text | "Saving...", "Creating...", etc. |
| Empty state | `text-center text-sm text-dim py-12` |
| Success feedback | `toast.success("Message")` via sonner |
| Error feedback | `toast.error("Message")` via sonner |
| Copy feedback | Icon switches `Copy` → `Check` (teal) for 2s |

---

## Responsive Behavior

- **Breakpoints**: mobile-first with `md:` (768px) and `lg:` (1200px)
- **Detail page sidebar**: stacks below content on mobile, fixed 320px right column on `lg:`
- **Status cards**: 2 cols → 3 cols on `md:` → 4 cols based on item count
- **Tables**: horizontally scrollable on mobile, resizable columns on desktop
- **Navigation sidebar**: fixed `w-60`, no mobile collapse (MVP)

---

## Toast Notifications

Via `sonner`. Keep messages short and consistent:

```tsx
toast.success("Entity saved");       // past tense, no period
toast.error("Failed to save entity"); // "Failed to {action}"
```

Never use `toast.info()` or `toast.warning()` — keep to success/error only.

---

## Naming Conventions

| What | Convention | Example |
|------|-----------|---------|
| Page components | `{Entity}Page`, `{Entity}DetailPage` | `AlertsListPage`, `AgentDetailPage` |
| List page files | `pages/{entity}/index.tsx` | `pages/alerts/index.tsx` |
| Detail page files | `pages/{entity}/detail.tsx` | `pages/alerts/detail.tsx` |
| Hook files | `hooks/use-{name}.ts` | `hooks/use-table-state.ts` |
| Component files | kebab-case | `detail-page-header.tsx` |
| Table column defs | `SCREAMING_SNAKE` const | `const AK_COLUMNS: ColumnDef[]` |
| Route names | `{entity}Route`, `{entity}DetailRoute` | `agentsRoute`, `agentDetailRoute` |
| Query keys | `[entity]` or `[entity, uuid]` | `["alerts"]`, `["alert", uuid]` |
| Mutation hooks | `use{Action}{Entity}` | `usePatchAlert`, `useCreateAgent` |
| localStorage keys | `calseta:{feature}` or `table-col-widths:{key}` | `calseta:dashboard-grid` |
