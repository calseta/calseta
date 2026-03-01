import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { relativeTime, severityColor, statusColor } from "@/lib/format";
import { ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUSES = [
  "pending_enrichment",
  "enriched",
  "Open",
  "Triaging",
  "Escalated",
  "Closed",
];
const SEVERITIES = [
  "Critical",
  "High",
  "Medium",
  "Low",
  "Informational",
  "Pending",
];

export function AlertsListPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const [source, setSource] = useState<string>("");

  const { data, isLoading } = useAlerts({
    page,
    page_size: 25,
    status: status || undefined,
    severity: severity || undefined,
    source_name: source || undefined,
  });

  const alerts = data?.data ?? [];
  const meta = data?.meta;
  const hasFilters = !!(status || severity || source);

  return (
    <AppLayout title="Alerts">
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
            <SelectTrigger className="w-44 bg-card border-border text-sm">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={severity} onValueChange={(v) => { setSeverity(v); setPage(1); }}>
            <SelectTrigger className="w-40 bg-card border-border text-sm">
              <SelectValue placeholder="All severities" />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {SEVERITIES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-dim" />
            <Input
              placeholder="Source name..."
              value={source}
              onChange={(e) => { setSource(e.target.value); setPage(1); }}
              className="w-44 pl-9 bg-card border-border text-sm"
            />
          </div>

          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setStatus("");
                setSeverity("");
                setSource("");
                setPage(1);
              }}
              className="text-dim hover:text-foreground"
            >
              <X className="h-3.5 w-3.5 mr-1" />
              Clear
            </Button>
          )}

          {meta && (
            <span className="ml-auto text-xs text-dim">
              {meta.total} alert{meta.total !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Severity</TableHead>
                <TableHead className="text-dim text-xs">Title</TableHead>
                <TableHead className="text-dim text-xs">Status</TableHead>
                <TableHead className="text-dim text-xs">Source</TableHead>
                <TableHead className="text-dim text-xs">Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 10 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-60" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-24" /></TableCell>
                    </TableRow>
                  ))
                : alerts.map((alert) => (
                    <TableRow
                      key={alert.uuid}
                      className="border-border hover:bg-accent/50 cursor-pointer"
                    >
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px] font-medium", severityColor(alert.severity))}
                        >
                          {alert.severity}
                        </Badge>
                      </TableCell>
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
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", statusColor(alert.status))}
                        >
                          {alert.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {alert.source_name}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {relativeTime(alert.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && alerts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-dim py-12">
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
