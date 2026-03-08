import { Link } from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAlerts } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate, severityColor, statusColor, enrichmentStatusColor } from "@/lib/format";
import { ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { CopyableText } from "@/components/copyable-text";
import { SortableColumnHeader } from "@/components/sortable-column-header";
import { ColumnFilterPopover } from "@/components/column-filter-popover";

const COLUMNS: ColumnDef[] = [
  { key: "title", initialWidth: 420, minWidth: 200 },
  { key: "uuid", initialWidth: 280, minWidth: 200 },
  { key: "status", initialWidth: 100, minWidth: 80 },
  { key: "enrichment", initialWidth: 100, minWidth: 80 },
  { key: "severity", initialWidth: 100, minWidth: 80 },
  { key: "source", initialWidth: 110, minWidth: 80 },
  { key: "time", initialWidth: 160, minWidth: 120 },
];

const STATUS_OPTIONS = [
  { value: "Open", label: "Open", colorClass: statusColor("Open") },
  { value: "Triaging", label: "Triaging", colorClass: statusColor("Triaging") },
  { value: "Escalated", label: "Escalated", colorClass: statusColor("Escalated") },
  { value: "Closed", label: "Closed", colorClass: statusColor("Closed") },
];

const ENRICHMENT_STATUS_OPTIONS = [
  { value: "Pending", label: "Pending", colorClass: enrichmentStatusColor("Pending") },
  { value: "Enriched", label: "Enriched", colorClass: enrichmentStatusColor("Enriched") },
  { value: "Failed", label: "Failed", colorClass: enrichmentStatusColor("Failed") },
];

const SEVERITY_OPTIONS = [
  { value: "Critical", label: "Critical", colorClass: severityColor("Critical") },
  { value: "High", label: "High", colorClass: severityColor("High") },
  { value: "Medium", label: "Medium", colorClass: severityColor("Medium") },
  { value: "Low", label: "Low", colorClass: severityColor("Low") },
  { value: "Informational", label: "Informational", colorClass: severityColor("Informational") },
  { value: "Pending", label: "Pending", colorClass: severityColor("Pending") },
];

const SOURCE_OPTIONS = [
  { value: "sentinel", label: "Sentinel" },
  { value: "elastic", label: "Elastic" },
  { value: "splunk", label: "Splunk" },
  { value: "generic", label: "Generic" },
];

// Map UI column keys to API sort_by values
const SORT_KEY_MAP: Record<string, string> = {
  title: "title",
  status: "status",
  severity: "severity",
  source: "source_name",
  time: "occurred_at",
};

export function AlertsListPage() {
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
  } = useTableState({ status: [] as string[], severity: [] as string[], source_name: [] as string[], enrichment_status: [] as string[] });

  const { data, isLoading, refetch, isFetching } = useAlerts(params);

  const alerts = data?.data ?? [];
  const meta = data?.meta;

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

  return (
    <AppLayout title="Alerts">
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
                {meta.total} alert{meta.total !== 1 ? "s" : ""}
                {hasActiveFilters && (
                  <span className="text-teal ml-1">(filtered)</span>
                )}
              </span>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="alerts" columns={COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="title" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Title"
                    sortKey="title"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="uuid" className="text-dim text-xs">UUID</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Status"
                    sortKey="status"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Status"
                        options={STATUS_OPTIONS}
                        selected={filters.status}
                        onChange={(v) => updateFilter("status", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="enrichment" className="text-dim text-xs">
                  <div className="flex items-center gap-1">
                    <span>Enrichment</span>
                    <ColumnFilterPopover
                      label="Enrichment"
                      options={ENRICHMENT_STATUS_OPTIONS}
                      selected={filters.enrichment_status}
                      onChange={(v) => updateFilter("enrichment_status", v)}
                    />
                  </div>
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
                <ResizableTableHead columnKey="time" className="text-dim text-xs">
                  <SortableColumnHeader
                    label="Time (UTC)"
                    sortKey="time"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 10 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-5 w-60" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-32" /></TableCell>
                    </TableRow>
                  ))
                : alerts.map((alert) => (
                    <TableRow
                      key={alert.uuid}
                      className="border-border hover:bg-accent/50 cursor-pointer"
                    >
                      <TableCell className="truncate">
                        <Link
                          to="/alerts/$uuid"
                          params={{ uuid: alert.uuid }}
                          className="text-sm text-foreground hover:text-teal-light transition-colors"
                        >
                          {alert.title}
                        </Link>
                        {alert.tags.length > 0 && (
                          <div className="mt-1 flex gap-1">
                            {alert.tags.slice(0, 3).map((t) => (
                              <span
                                key={t}
                                className="text-[10px] text-dim bg-surface-hover px-1.5 py-0.5 rounded"
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <CopyableText
                          text={alert.uuid}
                          mono
                          className="text-[11px] text-dim"
                        />
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", statusColor(alert.status))}
                        >
                          {alert.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", enrichmentStatusColor(alert.enrichment_status))}
                        >
                          {alert.enrichment_status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px] font-medium", severityColor(alert.severity))}
                        >
                          {alert.severity}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {alert.source_name}
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">
                        {formatDate(alert.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && alerts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No alerts found
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
