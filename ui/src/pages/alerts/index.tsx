import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useAlerts } from "@/hooks/use-api";
import { formatDate, severityColor, statusColor } from "@/lib/format";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { CopyableText } from "@/components/copyable-text";

export function AlertsListPage() {
  const [page, setPage] = useState(1);

  const { data, isLoading, refetch, isFetching } = useAlerts({
    page,
    page_size: 25,
  });

  const alerts = data?.data ?? [];
  const meta = data?.meta;

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
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Title</TableHead>
                <TableHead className="text-dim text-xs">UUID</TableHead>
                <TableHead className="text-dim text-xs">Status</TableHead>
                <TableHead className="text-dim text-xs">Severity</TableHead>
                <TableHead className="text-dim text-xs">Source</TableHead>
                <TableHead className="text-dim text-xs">Time (UTC)</TableHead>
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
                      <TableCell>
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
          </Table>
        </div>

        {/* Pagination */}
        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="bg-card border-border text-muted-foreground"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs text-dim">
              Page {meta.page} of {meta.total_pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
              className="bg-card border-border text-muted-foreground"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
