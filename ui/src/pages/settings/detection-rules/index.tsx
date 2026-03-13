import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ResizableTable,
  ResizableTableHead,
  type ColumnDef,
} from "@/components/ui/resizable-table";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useDetectionRules,
  useCreateDetectionRule,
  useDeleteDetectionRule,
} from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate, severityColor } from "@/lib/format";
import { CopyableText } from "@/components/copyable-text";
import { SortableColumnHeader } from "@/components/sortable-column-header";
import { ColumnFilterPopover } from "@/components/column-filter-popover";
import { TablePagination } from "@/components/table-pagination";
import { Plus, Trash2, RefreshCw, X, Save, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const DR_COLUMNS: ColumnDef[] = [
  { key: "name", initialWidth: 380, minWidth: 200 },
  { key: "uuid", initialWidth: 280, minWidth: 200 },
  { key: "source", initialWidth: 110, minWidth: 80 },
  { key: "severity", initialWidth: 90, minWidth: 70 },
  { key: "mitre", initialWidth: 200, minWidth: 100 },
  { key: "created", initialWidth: 160, minWidth: 120 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

const SOURCE_OPTIONS = [
  { value: "sentinel", label: "Sentinel" },
  { value: "elastic", label: "Elastic" },
  { value: "splunk", label: "Splunk" },
  { value: "generic", label: "Generic" },
];

const SEVERITY_OPTIONS = [
  { value: "Critical", label: "Critical", colorClass: severityColor("Critical") },
  { value: "High", label: "High", colorClass: severityColor("High") },
  { value: "Medium", label: "Medium", colorClass: severityColor("Medium") },
  { value: "Low", label: "Low", colorClass: severityColor("Low") },
  { value: "Informational", label: "Informational", colorClass: severityColor("Informational") },
  { value: "Pending", label: "Pending", colorClass: severityColor("Pending") },
];

const SEVERITY_VALUES = ["Critical", "High", "Medium", "Low", "Informational", "Pending"];

// Map UI column keys to API sort_by values
const SORT_KEY_MAP: Record<string, string> = {
  name: "name",
  source: "source_name",
  severity: "severity",
  created: "created_at",
};

export function DetectionRulesPage() {
  const {
    page,
    setPage,
    pageSize,
    handlePageSizeChange,
    sort,
    updateSort,
    filters,
    updateFilter,
    clearAll,
    hasActiveFiltersOrSort,
    hasActiveFilters,
    params,
  } = useTableState({ source_name: [] as string[], severity: [] as string[] });

  const { data, isLoading, refetch, isFetching } = useDetectionRules(params);
  const createRule = useCreateDetectionRule();
  const deleteRule = useDeleteDetectionRule();
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);

  // Create form state
  const [createDraft, setCreateDraft] = useState({
    name: "",
    source_rule_id: "",
    source_name: "",
    severity: "",
    run_frequency: "",
    created_by: "",
    documentation: "",
    mitre_tactics: [] as string[],
    mitre_techniques: [] as string[],
    mitre_subtechniques: [] as string[],
    data_sources: [] as string[],
  });
  const [newTactic, setNewTactic] = useState("");
  const [newTechnique, setNewTechnique] = useState("");
  const [newSubtechnique, setNewSubtechnique] = useState("");
  const [newDataSource, setNewDataSource] = useState("");

  const rules = data?.data ?? [];
  const meta = data?.meta;

  // Sort handler maps UI column keys to API sort_by values
  function handleSort(uiKey: string) {
    const apiKey = SORT_KEY_MAP[uiKey] ?? uiKey;
    updateSort(apiKey);
  }

  // Reverse-map current sort column back to UI key
  const reverseSortKeyMap: Record<string, string> = Object.fromEntries(
    Object.entries(SORT_KEY_MAP).map(([ui, api]) => [api, ui]),
  );
  const uiSort = sort
    ? { column: reverseSortKeyMap[sort.column] ?? sort.column, order: sort.order }
    : null;

  function resetCreateDraft() {
    setCreateDraft({
      name: "",
      source_rule_id: "",
      source_name: "",
      severity: "",
      run_frequency: "",
      created_by: "",
      documentation: "",
      mitre_tactics: [],
      mitre_techniques: [],
      mitre_subtechniques: [],
      data_sources: [],
    });
    setNewTactic("");
    setNewTechnique("");
    setNewSubtechnique("");
    setNewDataSource("");
  }

  function updateDraft(key: string, value: unknown) {
    setCreateDraft((prev) => ({ ...prev, [key]: value }));
  }

  function addToList(key: string, value: string, resetFn: (v: string) => void) {
    const trimmed = value.trim();
    if (!trimmed) return;
    const list = (createDraft[key as keyof typeof createDraft] as string[]) ?? [];
    if (!list.includes(trimmed)) {
      updateDraft(key, [...list, trimmed]);
    }
    resetFn("");
  }

  function removeFromList(key: string, value: string) {
    const list = (createDraft[key as keyof typeof createDraft] as string[]) ?? [];
    updateDraft(key, list.filter((v) => v !== value));
  }

  function handleCreate() {
    createRule.mutate(
      {
        name: createDraft.name,
        source_rule_id: createDraft.source_rule_id || undefined,
        source_name: createDraft.source_name || undefined,
        severity: createDraft.severity || undefined,
        mitre_tactics: createDraft.mitre_tactics,
        mitre_techniques: createDraft.mitre_techniques,
        mitre_subtechniques: createDraft.mitre_subtechniques,
        data_sources: createDraft.data_sources,
        run_frequency: createDraft.run_frequency || undefined,
        created_by: createDraft.created_by || undefined,
        documentation: createDraft.documentation || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetCreateDraft();
          toast.success("Detection rule created");
        },
        onError: () => toast.error("Failed to create detection rule"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteRule.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Detection rule deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete detection rule"),
    });
  }

  return (
    <AppLayout title="Detection Rules">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            {hasActiveFiltersOrSort && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearAll}
                className="h-7 px-2 text-xs text-dim hover:text-foreground gap-1"
              >
                <X className="h-3 w-3" />
                Reset filters
              </Button>
            )}
            {meta && (
              <span className="text-xs text-dim">
                {meta.total} rule{meta.total !== 1 ? "s" : ""}
                {hasActiveFilters && (
                  <span className="text-teal ml-1">(filtered)</span>
                )}
              </span>
            )}
          </div>
          <Dialog
            open={open}
            onOpenChange={(v) => {
              setOpen(v);
              if (!v) resetCreateDraft();
            }}
          >
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Rule
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Detection Rule</DialogTitle>
              </DialogHeader>

              <div className="space-y-4 py-2">
                {/* Name */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Name *</Label>
                  <Input
                    value={createDraft.name}
                    onChange={(e) => updateDraft("name", e.target.value)}
                    className="bg-surface border-border text-sm"
                  />
                </div>

                {/* Source Rule ID + Source Name */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Source Rule ID</Label>
                    <Input
                      value={createDraft.source_rule_id}
                      onChange={(e) => updateDraft("source_rule_id", e.target.value)}
                      className="bg-surface border-border text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Source Name</Label>
                    <Input
                      value={createDraft.source_name}
                      onChange={(e) => updateDraft("source_name", e.target.value)}
                      className="bg-surface border-border text-sm"
                    />
                  </div>
                </div>

                {/* Severity + Run Frequency */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Severity</Label>
                    <Select value={createDraft.severity} onValueChange={(v) => updateDraft("severity", v)}>
                      <SelectTrigger className="bg-surface border-border text-sm">
                        <SelectValue placeholder="Select severity" />
                      </SelectTrigger>
                      <SelectContent>
                        {SEVERITY_VALUES.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Run Frequency</Label>
                    <Input
                      value={createDraft.run_frequency}
                      onChange={(e) => updateDraft("run_frequency", e.target.value)}
                      placeholder="e.g. 5m, 1h"
                      className="bg-surface border-border text-sm"
                    />
                  </div>
                </div>

                {/* Created By */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Created By</Label>
                  <Input
                    value={createDraft.created_by}
                    onChange={(e) => updateDraft("created_by", e.target.value)}
                    placeholder="Author name or team"
                    className="bg-surface border-border text-sm"
                  />
                </div>

                {/* MITRE ATT&CK */}
                <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">MITRE ATT&CK</span>

                  {/* Tactics */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Tactics</Label>
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {createDraft.mitre_tactics.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-teal bg-teal/10 border-teal/30 gap-1">
                          {t}
                          <button type="button" onClick={() => removeFromList("mitre_tactics", t)} className="hover:text-red-400">
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-1.5">
                      <Input
                        value={newTactic}
                        onChange={(e) => setNewTactic(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_tactics", newTactic, setNewTactic))}
                        placeholder="e.g. Execution"
                        className="bg-card border-border text-sm h-7"
                      />
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => addToList("mitre_tactics", newTactic, setNewTactic)}
                        className="h-7 px-2 border-border"
                      >
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  {/* Techniques */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Techniques</Label>
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {createDraft.mitre_techniques.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                          {t}
                          <button type="button" onClick={() => removeFromList("mitre_techniques", t)} className="hover:text-red-400">
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-1.5">
                      <Input
                        value={newTechnique}
                        onChange={(e) => setNewTechnique(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_techniques", newTechnique, setNewTechnique))}
                        placeholder="e.g. T1204"
                        className="bg-card border-border text-sm h-7"
                      />
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => addToList("mitre_techniques", newTechnique, setNewTechnique)}
                        className="h-7 px-2 border-border"
                      >
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  {/* Sub-techniques */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Sub-techniques</Label>
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {createDraft.mitre_subtechniques.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                          {t}
                          <button type="button" onClick={() => removeFromList("mitre_subtechniques", t)} className="hover:text-red-400">
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-1.5">
                      <Input
                        value={newSubtechnique}
                        onChange={(e) => setNewSubtechnique(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_subtechniques", newSubtechnique, setNewSubtechnique))}
                        placeholder="e.g. T1204.002"
                        className="bg-card border-border text-sm h-7"
                      />
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => addToList("mitre_subtechniques", newSubtechnique, setNewSubtechnique)}
                        className="h-7 px-2 border-border"
                      >
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Data Sources */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Data Sources</Label>
                  <div className="flex flex-wrap gap-1 mb-1.5">
                    {createDraft.data_sources.map((ds) => (
                      <Badge key={ds} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                        {ds}
                        <button type="button" onClick={() => removeFromList("data_sources", ds)} className="hover:text-red-400">
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <div className="flex gap-1.5">
                    <Input
                      value={newDataSource}
                      onChange={(e) => setNewDataSource(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("data_sources", newDataSource, setNewDataSource))}
                      placeholder="e.g. Endpoint File Creation Events"
                      className="bg-surface border-border text-sm"
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => addToList("data_sources", newDataSource, setNewDataSource)}
                      className="h-8 px-2 border-border"
                    >
                      <Plus className="h-3 w-3" />
                    </Button>
                  </div>
                </div>

                {/* Documentation */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Documentation</Label>
                  <Textarea
                    value={createDraft.documentation}
                    onChange={(e) => updateDraft("documentation", e.target.value)}
                    className="bg-surface border-border text-sm"
                    rows={3}
                  />
                </div>
              </div>

              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => { setOpen(false); resetCreateDraft(); }}
                  className="border-border"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={createRule.isPending || !createDraft.name.trim()}
                  className="bg-teal text-white hover:bg-teal-dim"
                >
                  {createRule.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5 mr-1.5" />
                  )}
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="detection-rules" columns={DR_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="name" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Name"
                    sortKey="name"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="uuid" className="text-dim text-xs">UUID</ResizableTableHead>
                <ResizableTableHead columnKey="source" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Source"
                    sortKey="source"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Source"
                        options={SOURCE_OPTIONS}
                        selected={filters.source_name}
                        onChange={(v) => updateFilter("source_name", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="severity" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Severity"
                    sortKey="severity"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Severity"
                        options={SEVERITY_OPTIONS}
                        selected={filters.severity}
                        onChange={(v) => updateFilter("severity", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="mitre" className="text-dim text-xs">MITRE</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Created (UTC)"
                    sortKey="created"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : rules.map((rule) => (
                    <TableRow key={rule.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          to="/manage/detection-rules/$uuid"
                          params={{ uuid: rule.uuid }}
                          className="text-sm text-foreground hover:text-teal-light transition-colors block truncate"
                          title={rule.name}
                        >
                          {rule.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <CopyableText text={rule.uuid} mono className="text-[11px] text-dim" />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{rule.source_name ?? "—"}</TableCell>
                      <TableCell>
                        {rule.severity ? (
                          <Badge
                            variant="outline"
                            className={cn("text-[11px] font-medium", severityColor(rule.severity))}
                          >
                            {rule.severity}
                          </Badge>
                        ) : (
                          <span className="text-xs text-dim">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {rule.mitre_tactics?.length > 0 && <span>{rule.mitre_tactics.join(", ")}</span>}
                        {rule.mitre_techniques?.length > 0 && <span className="ml-1">/ {rule.mitre_techniques.join(", ")}</span>}
                        {!rule.mitre_tactics?.length && !rule.mitre_techniques?.length && "—"}
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(rule.created_at)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget({ uuid: rule.uuid, name: rule.name })}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && rules.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No detection rules configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </ResizableTable>
        </div>

        {meta && (
          <TablePagination
            page={page}
            pageSize={pageSize}
            totalPages={meta.total_pages}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Detection Rule"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
