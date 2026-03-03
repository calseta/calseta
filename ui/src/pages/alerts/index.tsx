import { useState } from "react";
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
import { usePageSize } from "@/hooks/use-page-size";
import { formatDate, severityColor, statusColor } from "@/lib/format";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { CopyableText } from "@/components/copyable-text";

const COLUMNS: ColumnDef[] = [
  { key: "title", initialWidth: 320, minWidth: 160 },
  { key: "uuid", initialWidth: 140, minWidth: 100 },
  { key: "status", initialWidth: 110, minWidth: 80 },
  { key: "severity", initialWidth: 100, minWidth: 80 },
  { key: "source", initialWidth: 110, minWidth: 80 },
  { key: "time", initialWidth: 160, minWidth: 120 },
];

export function AlertsListPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = usePageSize();

  const { data, isLoading, refetch, isFetching } = useAlerts({
    page,
    page_size: pageSize,
  });

  const alerts = data?.data ?? [];
  const meta = data?.meta;

  function handlePageSizeChange(value: string) {
    setPageSize(Number(value));
    setPage(1);
  }

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
            {meta && (
              <span className="text-xs text-dim">
                {meta.total} alert{meta.total !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="alerts" columns={COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="title" className="text-dim text-xs">Title</ResizableTableHead>
                <ResizableTableHead columnKey="uuid" className="text-dim text-xs">UUID</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Status</ResizableTableHead>
                <ResizableTableHead columnKey="severity" className="text-dim text-xs">Severity</ResizableTableHead>
                <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
                <ResizableTableHead columnKey="time" className="text-dim text-xs">Time (UTC)</ResizableTableHead>
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
                  <TableCell colSpan={6} className="text-center text-sm text-dim py-12">
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
                <SelectTrigger className="h-7 w-[62px] bg-card border-border text-xs text-dim">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="25">25</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
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
