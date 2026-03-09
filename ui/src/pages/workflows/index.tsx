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
import { useWorkflows, useCreateWorkflow } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate, riskColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CopyableText } from "@/components/copyable-text";
import { SortableColumnHeader } from "@/components/sortable-column-header";
import { ColumnFilterPopover } from "@/components/column-filter-popover";
import { ShieldCheck, Code, Plus, RefreshCw, ChevronLeft, ChevronRight, X } from "lucide-react";

const WF_COLUMNS: ColumnDef[] = [
  { key: "name", initialWidth: 380, minWidth: 200 },
  { key: "uuid", initialWidth: 280, minWidth: 200 },
  { key: "state", initialWidth: 80, minWidth: 70 },
  { key: "type", initialWidth: 110, minWidth: 80 },
  { key: "indicators", initialWidth: 180, minWidth: 120 },
  { key: "risk", initialWidth: 80, minWidth: 70 },
  { key: "approval", initialWidth: 80, minWidth: 60 },
  { key: "version", initialWidth: 70, minWidth: 60 },
  { key: "updated", initialWidth: 130, minWidth: 100 },
];

const STATE_OPTIONS = [
  { value: "active", label: "active", colorClass: "text-teal bg-teal/10 border-teal/30" },
  { value: "draft", label: "draft", colorClass: "text-amber bg-amber/10 border-amber/30" },
  { value: "inactive", label: "inactive", colorClass: "text-dim bg-dim/10 border-dim/30" },
];

const RISK_OPTIONS = [
  { value: "critical", label: "critical", colorClass: riskColor("critical") },
  { value: "high", label: "high", colorClass: riskColor("high") },
  { value: "medium", label: "medium", colorClass: riskColor("medium") },
  { value: "low", label: "low", colorClass: riskColor("low") },
];

// Map UI column keys to API sort_by values
const SORT_KEY_MAP: Record<string, string> = {
  name: "name",
  state: "state",
  risk: "risk_level",
  updated: "updated_at",
};

const WORKFLOW_TYPE_OPTIONS = ["indicator", "enrichment", "response", "notification", "containment"];
const INDICATOR_TYPE_OPTIONS = ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"];

const INITIAL_CREATE_STATE: Record<string, unknown> = {
  name: "",
  workflow_type: "indicator",
  risk_level: "low",
  approval_mode: "always",
  approval_channel: "",
  approval_timeout_seconds: 3600,
  indicator_types: [] as string[],
  timeout_seconds: 30,
  retry_count: 0,
};

export function WorkflowsListPage() {
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
  } = useTableState({ state: [] as string[], risk_level: [] as string[] });

  const { data, isLoading, refetch, isFetching } = useWorkflows(params);
  const createWorkflow = useCreateWorkflow();
  const workflows = data?.data ?? [];
  const meta = data?.meta;

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>({ ...INITIAL_CREATE_STATE });

  function updateDraft(key: string, value: unknown) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  // Sort handler maps UI column keys to API sort_by values
  function handleSort(uiKey: string) {
    const apiKey = SORT_KEY_MAP[uiKey] ?? uiKey;
    updateSort(apiKey);
  }

  // Reverse-map current sort column back to UI key for SortableColumnHeader comparison
  const reverseSortKeyMap: Record<string, string> = Object.fromEntries(
    Object.entries(SORT_KEY_MAP).map(([ui, api]) => [api, ui]),
  );
  const uiSort = sort
    ? { column: reverseSortKeyMap[sort.column] ?? sort.column, order: sort.order }
    : null;

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    createWorkflow.mutate(
      {
        ...draft,
        // Send a minimal default code so the API doesn't reject it
        code: "async def run(ctx):\n    return ctx.result.success(message=\"Workflow created\", data={})\n",
      },
      {
        onSuccess: () => {
          setOpen(false);
          setDraft({ ...INITIAL_CREATE_STATE });
          toast.success("Workflow created");
        },
        onError: () => toast.error("Failed to create workflow"),
      },
    );
  }

  return (
    <AppLayout title="Workflows">
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
                {meta.total} workflow{meta.total !== 1 ? "s" : ""}
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
                Create Workflow
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Workflow</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-4 py-2">
                {/* Name */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Name</Label>
                  <Input
                    value={(draft.name as string) ?? ""}
                    onChange={(e) => updateDraft("name", e.target.value)}
                    required
                    className="bg-surface border-border text-sm"
                    placeholder="e.g. Revoke User Sessions"
                  />
                </div>

                {/* Type + Risk Level */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Type</Label>
                    <Select
                      value={(draft.workflow_type as string) ?? "indicator"}
                      onValueChange={(v) => updateDraft("workflow_type", v)}
                    >
                      <SelectTrigger className="bg-surface border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-card border-border">
                        {WORKFLOW_TYPE_OPTIONS.map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Risk Level</Label>
                    <Select
                      value={(draft.risk_level as string) ?? "low"}
                      onValueChange={(v) => updateDraft("risk_level", v)}
                    >
                      <SelectTrigger className="bg-surface border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-card border-border">
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Indicator Types */}
                <div className="space-y-1.5">
                  <Label className="text-sm text-muted-foreground">Indicator Types</Label>
                  <div className="flex flex-wrap gap-2">
                    {INDICATOR_TYPE_OPTIONS.map((t) => {
                      const types = (draft.indicator_types as string[]) ?? [];
                      const selected = types.includes(t);
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => {
                            const next = selected
                              ? types.filter((x) => x !== t)
                              : [...types, t];
                            updateDraft("indicator_types", next);
                          }}
                          className={cn(
                            "px-2.5 py-1 rounded-md text-xs border transition-colors",
                            selected
                              ? "bg-teal/15 border-teal/40 text-teal-light"
                              : "bg-surface border-border text-dim hover:border-teal/30",
                          )}
                        >
                          {t}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Timeout + Retry */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Timeout (seconds)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={draft.timeout_seconds as number}
                      onChange={(e) => updateDraft("timeout_seconds", parseInt(e.target.value) || 1)}
                      className="bg-surface border-border text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Retry Count</Label>
                    <Input
                      type="number"
                      min={0}
                      value={draft.retry_count as number}
                      onChange={(e) => updateDraft("retry_count", parseInt(e.target.value) || 0)}
                      className="bg-surface border-border text-sm"
                    />
                  </div>
                </div>

                {/* Approval Gate */}
                <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Approval Mode</Label>
                    <Select
                      value={(draft.approval_mode as string) ?? "always"}
                      onValueChange={(v) => updateDraft("approval_mode", v)}
                    >
                      <SelectTrigger className="bg-card border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-card border-border">
                        <SelectItem value="always">Always</SelectItem>
                        <SelectItem value="agent_only">Agent Only</SelectItem>
                        <SelectItem value="never">Never</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {(draft.approval_mode as string) !== "never" && (
                    <>
                      <div className="space-y-1.5">
                        <Label className="text-sm text-muted-foreground">Approval Channel</Label>
                        <Input
                          value={(draft.approval_channel as string) ?? ""}
                          onChange={(e) => updateDraft("approval_channel", e.target.value)}
                          placeholder="C0123456789"
                          className="bg-card border-border text-sm font-mono"
                        />
                        <p className="text-[10px] text-dim">
                          Slack channel ID or Teams webhook URL
                        </p>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-sm text-muted-foreground">Approval Timeout (seconds)</Label>
                        <Input
                          type="number"
                          min={60}
                          value={draft.approval_timeout_seconds as number}
                          onChange={(e) => updateDraft("approval_timeout_seconds", parseInt(e.target.value) || 300)}
                          className="bg-card border-border text-sm"
                        />
                      </div>
                    </>
                  )}
                </div>

                <Button
                  type="submit"
                  disabled={createWorkflow.isPending || !(draft.name as string)?.trim()}
                  className="w-full bg-teal text-white hover:bg-teal-dim"
                >
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="workflows" columns={WF_COLUMNS}>
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
                <ResizableTableHead columnKey="state" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="State"
                    sortKey="state"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="State"
                        options={STATE_OPTIONS}
                        selected={filters.state}
                        onChange={(v) => updateFilter("state", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="type" className="text-dim text-xs">Type</ResizableTableHead>
                <ResizableTableHead columnKey="indicators" className="text-dim text-xs">Indicators</ResizableTableHead>
                <ResizableTableHead columnKey="risk" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Risk"
                    sortKey="risk"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Risk"
                        options={RISK_OPTIONS}
                        selected={filters.risk_level}
                        onChange={(v) => updateFilter("risk_level", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="approval" className="text-dim text-xs">Approval</ResizableTableHead>
                <ResizableTableHead columnKey="version" className="text-dim text-xs">Version</ResizableTableHead>
                <ResizableTableHead columnKey="updated" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Updated"
                    sortKey="updated"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 9 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-5 w-20" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : workflows.map((wf) => (
                    <TableRow
                      key={wf.uuid}
                      className="border-border hover:bg-accent/50"
                    >
                      <TableCell>
                        <Link
                          to="/workflows/$uuid"
                          params={{ uuid: wf.uuid }}
                          className="text-sm text-foreground hover:text-teal-light transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            {wf.is_system ? (
                              <ShieldCheck className="h-3.5 w-3.5 text-teal" />
                            ) : (
                              <Code className="h-3.5 w-3.5 text-dim" />
                            )}
                            {wf.name}
                          </div>
                        </Link>
                      </TableCell>
                      <TableCell className="overflow-hidden">
                        <CopyableText text={wf.uuid} mono className="text-[11px] text-dim truncate block" />
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[11px]",
                            wf.state === "active"
                              ? "text-teal bg-teal/10 border-teal/30"
                              : wf.state === "draft"
                                ? "text-amber bg-amber/10 border-amber/30"
                                : "text-dim bg-dim/10 border-dim/30",
                          )}
                        >
                          {wf.state}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {wf.workflow_type ?? "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {wf.indicator_types?.length ? (
                            wf.indicator_types.map((t: string) => (
                              <Badge
                                key={t}
                                variant="outline"
                                className="text-[10px] font-mono text-purple-400 bg-purple-400/10 border-purple-400/30"
                              >
                                {t}
                              </Badge>
                            ))
                          ) : (
                            <span className="text-dim">—</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", riskColor(wf.risk_level))}
                        >
                          {wf.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[11px]",
                            wf.approval_mode === "always"
                              ? "text-amber bg-amber/10 border-amber/30"
                              : wf.approval_mode === "agent_only"
                                ? "text-teal bg-teal/10 border-teal/30"
                                : "text-dim bg-dim/10 border-dim/30",
                          )}
                        >
                          {wf.approval_mode === "agent_only" ? "agent only" : wf.approval_mode}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-dim font-mono">
                        v{wf.code_version}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {formatDate(wf.updated_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && workflows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-sm text-dim py-12">
                    No workflows configured
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
    </AppLayout>
  );
}
