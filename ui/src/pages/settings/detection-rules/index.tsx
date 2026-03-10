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
import { Plus, Trash2, RefreshCw, ChevronLeft, ChevronRight, X } from "lucide-react";
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

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);

    const tacticsRaw = (fd.get("mitre_tactics") as string).trim();
    const techniquesRaw = (fd.get("mitre_techniques") as string).trim();
    const subtechniquesRaw = (fd.get("mitre_subtechniques") as string).trim();
    const dataSourcesRaw = (fd.get("data_sources") as string).trim();

    createRule.mutate(
      {
        name: fd.get("name") as string,
        source_rule_id: (fd.get("source_rule_id") as string) || undefined,
        source_name: (fd.get("source_name") as string) || undefined,
        severity: (fd.get("severity") as string) || undefined,
        mitre_tactics: tacticsRaw ? tacticsRaw.split(",").map((s) => s.trim()) : [],
        mitre_techniques: techniquesRaw ? techniquesRaw.split(",").map((s) => s.trim()) : [],
        mitre_subtechniques: subtechniquesRaw ? subtechniquesRaw.split(",").map((s) => s.trim()) : [],
        data_sources: dataSourcesRaw ? dataSourcesRaw.split(",").map((s) => s.trim()) : [],
        run_frequency: (fd.get("run_frequency") as string) || undefined,
        created_by: (fd.get("created_by") as string) || undefined,
        documentation: (fd.get("documentation") as string) || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
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
          <Dialog open={open} onOpenChange={setOpen}>
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
              <form onSubmit={handleCreate} className="space-y-3">
                <Field label="Name" name="name" required />
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Source Rule ID" name="source_rule_id" />
                  <Field label="Source Name" name="source_name" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Severity" name="severity" placeholder="e.g. High, Critical" />
                  <Field label="Run Frequency" name="run_frequency" placeholder="e.g. 5m, 1h" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Tactics</Label>
                  <Input name="mitre_tactics" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: Initial Access, Execution" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Techniques</Label>
                  <Input name="mitre_techniques" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: T1566, T1059" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Sub-techniques</Label>
                  <Input name="mitre_subtechniques" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: T1566.001, T1059.001" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Data Sources</Label>
                  <Input name="data_sources" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: Process, Network Traffic" />
                </div>
                <Field label="Created By" name="created_by" placeholder="Author name or team" />
                <div>
                  <Label className="text-xs text-muted-foreground">Documentation</Label>
                  <Textarea name="documentation" className="mt-1 bg-surface border-border text-sm" rows={3} />
                </div>
                <Button type="submit" disabled={createRule.isPending} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Create
                </Button>
              </form>
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

        {/* Pagination */}
        {meta && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-dim">Rows per page</span>
              <Select value={String(pageSize)} onValueChange={handlePageSizeChange}>
                <SelectTrigger className="h-7 w-[80px] bg-card border-border text-xs text-dim">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="25">25</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                  <SelectItem value="250">250</SelectItem>
                  <SelectItem value="500">500</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-dim">
                Page {meta.page} of {meta.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="h-7 w-7 p-0 bg-card border-border text-muted-foreground"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= meta.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="h-7 w-7 p-0 bg-card border-border text-muted-foreground"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
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

function Field({
  label,
  name,
  required,
  placeholder,
}: {
  label: string;
  name: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input name={name} required={required} placeholder={placeholder} className="mt-1 bg-surface border-border text-sm" />
    </div>
  );
}
