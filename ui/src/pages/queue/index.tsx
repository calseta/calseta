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
import { Skeleton } from "@/components/ui/skeleton";
import { TablePagination } from "@/components/table-pagination";
import { ColumnFilterPopover } from "@/components/column-filter-popover";
import { useAlertQueue } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { severityColor, enrichmentStatusColor, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw, X } from "lucide-react";

const COLUMNS: ColumnDef[] = [
  { key: "severity", initialWidth: 100, minWidth: 80 },
  { key: "title", initialWidth: 380, minWidth: 200 },
  { key: "source", initialWidth: 110, minWidth: 80 },
  { key: "ingested_at", initialWidth: 140, minWidth: 100 },
  { key: "indicators", initialWidth: 100, minWidth: 70 },
  { key: "enrichment", initialWidth: 110, minWidth: 80 },
];

const SEVERITY_OPTIONS = [
  { value: "Critical", label: "Critical", colorClass: severityColor("Critical") },
  { value: "High", label: "High", colorClass: severityColor("High") },
  { value: "Medium", label: "Medium", colorClass: severityColor("Medium") },
  { value: "Low", label: "Low", colorClass: severityColor("Low") },
  { value: "Informational", label: "Informational", colorClass: severityColor("Informational") },
  { value: "Pending", label: "Pending", colorClass: severityColor("Pending") },
];


export function QueuePage() {
  const {
    page,
    setPage,
    pageSize,
    handlePageSizeChange,
    filters,
    updateFilter,
    clearAll,
    hasActiveFiltersOrSort,
    hasActiveFilters,
    params,
  } = useTableState({ severity: [] as string[], status: [] as string[] });

  const { data, isLoading, refetch, isFetching } = useAlertQueue(params);

  const alerts = data?.data ?? [];
  const meta = data?.meta;

  return (
    <AppLayout title="Alert Queue">
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
          <span className="text-xs text-dim">Auto-refreshes every 30s</span>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="alert-queue" columns={COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="severity" className="text-dim text-xs">
                  <div className="flex items-center gap-1">
                    <span>Severity</span>
                    <ColumnFilterPopover
                      label="Severity"
                      options={SEVERITY_OPTIONS}
                      selected={filters.severity}
                      onChange={(v) => updateFilter("severity", v)}
                    />
                  </div>
                </ResizableTableHead>
                <ResizableTableHead columnKey="title" className="text-dim text-xs">Title</ResizableTableHead>
                <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
                <ResizableTableHead columnKey="ingested_at" className="text-dim text-xs">Ingested</ResizableTableHead>
                <ResizableTableHead columnKey="indicators" className="text-dim text-xs">Indicators</ResizableTableHead>
                <ResizableTableHead columnKey="enrichment" className="text-dim text-xs">
                  <div className="flex items-center gap-1">
                    <span>Enrichment</span>
                  </div>
                </ResizableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-56" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-10" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                    </TableRow>
                  ))
                : alerts.map((alert) => (
                    <TableRow key={alert.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px] font-medium", severityColor(alert.severity))}
                        >
                          {alert.severity}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[360px]">
                        <Link
                          to="/alerts/$uuid"
                          params={{ uuid: alert.uuid }}
                          search={{ tab: "indicators" }}
                          className="text-sm text-foreground hover:text-teal-light transition-colors truncate block"
                        >
                          {alert.title}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {alert.source_name}
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">
                        {relativeTime(alert.ingested_at)}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {Array.isArray(alert.indicators) ? alert.indicators.length : 0}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", enrichmentStatusColor(alert.enrichment_status))}
                        >
                          {alert.enrichment_status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && alerts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-dim py-20">
                    Queue is empty
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
    </AppLayout>
  );
}
