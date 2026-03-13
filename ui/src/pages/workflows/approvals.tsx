import { toast } from "sonner";
import { Link } from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { TablePagination } from "@/components/table-pagination";
import {
  useApprovals,
  useApproveWorkflow,
  useRejectWorkflow,
} from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { WorkflowApproval } from "@/lib/types";
import { CheckCircle, XCircle, Clock, Shield, Copy, Check, RefreshCw } from "lucide-react";
import { useState, useCallback } from "react";

const APPROVAL_COLUMNS: ColumnDef[] = [
  { key: "workflow", initialWidth: 180, minWidth: 120 },
  { key: "status", initialWidth: 85, minWidth: 70 },
  { key: "triggered_by", initialWidth: 60, minWidth: 60 },
  { key: "target", initialWidth: 240, minWidth: 140 },
  { key: "reason", initialWidth: 220, minWidth: 120 },
  { key: "confidence", initialWidth: 80, minWidth: 60 },
  { key: "expires", initialWidth: 130, minWidth: 100 },
  { key: "actions", initialWidth: 195, minWidth: 180 },
];

/** Defense-in-depth: a request is actionable only if the backend says pending
 *  AND the expiry timestamp hasn't passed on the client clock. */
function isActionable(req: WorkflowApproval): boolean {
  return req.status === "pending" && new Date(req.expires_at) > new Date();
}

/** Derive display status — treat pending-but-expired as "expired" even if
 *  the backend hasn't materialized it yet. */
function displayStatus(req: WorkflowApproval): string {
  if (req.status === "pending" && new Date(req.expires_at) <= new Date()) {
    return "expired";
  }
  return req.status;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "approved") return <CheckCircle className="h-3.5 w-3.5 text-teal" />;
  if (status === "rejected" || status === "expired")
    return <XCircle className="h-3.5 w-3.5 text-red-threat" />;
  return <Clock className="h-3.5 w-3.5 text-amber" />;
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "pending":
      return "text-amber bg-amber/10 border-amber/30";
    case "approved":
      return "text-teal bg-teal/10 border-teal/30";
    case "rejected":
    case "expired":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default:
      return "text-dim bg-dim/10 border-dim/30";
  }
}

/** Copyable badge — copy icon appears on the left on hover, expanding the badge. */
function CopyableBadge({
  copyValue,
  className,
  children,
}: {
  copyValue: string;
  className?: string;
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      navigator.clipboard.writeText(copyValue).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    },
    [copyValue],
  );

  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[10px] font-mono cursor-pointer group/copy max-w-full transition-all",
        "pl-1.5 hover:pl-1",
        className,
      )}
      onClick={handleCopy}
    >
      <span className="w-0 overflow-hidden opacity-0 group-hover/copy:w-3.5 group-hover/copy:opacity-100 transition-all duration-150 shrink-0">
        {copied ? (
          <Check className="h-2.5 w-2.5 text-teal" />
        ) : (
          <Copy className="h-2.5 w-2.5" />
        )}
      </span>
      <span className="truncate">{children}</span>
    </Badge>
  );
}

/** Build target display from trigger_context. Shows indicator type:value
 *  or alert UUID depending on what's present, all inside a single badge. */
function TargetCell({ tc }: { tc: Record<string, unknown> }) {
  const indicatorType = tc.indicator_type as string | undefined;
  const indicatorValue = tc.indicator_value as string | undefined;
  const alertUuid = tc.alert_uuid as string | undefined;

  if (indicatorType && indicatorValue) {
    return (
      <CopyableBadge
        copyValue={indicatorValue}
        className="text-purple-400 bg-purple-400/10 border-purple-400/30 hover:border-purple-400/50"
      >
        {indicatorType}:{indicatorValue}
      </CopyableBadge>
    );
  }

  if (alertUuid) {
    return (
      <CopyableBadge
        copyValue={alertUuid}
        className="text-blue-400 bg-blue-400/10 border-blue-400/30 hover:border-blue-400/50"
      >
        alert:{alertUuid.slice(0, 8)}…
      </CopyableBadge>
    );
  }

  return <span className="text-xs text-dim">—</span>;
}

export function ApprovalsPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } = useTableState({});
  const { data, isLoading, refetch, isFetching } = useApprovals(params);
  const approve = useApproveWorkflow();
  const reject = useRejectWorkflow();
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);

  const approvals = data?.data ?? [];
  const meta = data?.meta;

  return (
    <AppLayout title="Workflow Approvals">
      <div className="space-y-4">
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
            {meta.total} approval{meta.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      <div className="rounded-lg border border-border bg-card">
        <ResizableTable storageKey="workflow-approvals" columns={APPROVAL_COLUMNS}>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <ResizableTableHead columnKey="workflow" className="text-dim text-xs">
                Workflow
              </ResizableTableHead>
              <ResizableTableHead columnKey="status" className="text-dim text-xs">
                Status
              </ResizableTableHead>
              <ResizableTableHead columnKey="triggered_by" className="text-dim text-xs">
                Triggered By
              </ResizableTableHead>
              <ResizableTableHead columnKey="target" className="text-dim text-xs">
                Target
              </ResizableTableHead>
              <ResizableTableHead columnKey="reason" className="text-dim text-xs">
                Reason
              </ResizableTableHead>
              <ResizableTableHead columnKey="confidence" className="text-dim text-xs">
                Confidence
              </ResizableTableHead>
              <ResizableTableHead columnKey="expires" className="text-dim text-xs">
                Expires
              </ResizableTableHead>
              <ResizableTableHead columnKey="actions" className="text-dim text-xs">
                Actions
              </ResizableTableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i} className="border-border">
                    {Array.from({ length: 8 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-5 w-20" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : approvals.map((req) => {
                  const shown = displayStatus(req);
                  const actionable = isActionable(req);
                  const tc = req.trigger_context ?? {};
                  return (
                    <TableRow key={req.uuid} className="border-border hover:bg-accent/50">
                      {/* Workflow */}
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <StatusIcon status={shown} />
                          {req.workflow_uuid ? (
                            <Link
                              to="/workflows/$uuid"
                              params={{ uuid: req.workflow_uuid }}
                              search={{ tab: "runs" }}
                              className="text-sm font-medium text-foreground hover:text-teal-light transition-colors truncate"
                            >
                              {req.workflow_name ?? "—"}
                            </Link>
                          ) : (
                            <span className="text-sm font-medium text-foreground truncate">
                              {req.workflow_name ?? "—"}
                            </span>
                          )}
                        </div>
                      </TableCell>

                      {/* Status */}
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", statusBadgeClass(shown))}
                        >
                          {shown}
                        </Badge>
                      </TableCell>

                      {/* Triggered By */}
                      <TableCell>
                        {req.trigger_agent_key_prefix ? (
                          <Link
                            to="/settings/api-keys"
                            className="text-xs font-mono text-foreground hover:text-teal-light transition-colors"
                          >
                            {req.trigger_agent_key_prefix}…
                          </Link>
                        ) : (
                          <span className="text-xs text-dim">{req.trigger_type}</span>
                        )}
                      </TableCell>

                      {/* Target */}
                      <TableCell>
                        <TargetCell tc={tc} />
                      </TableCell>

                      {/* Reason */}
                      <TableCell>
                        {req.trigger_context &&
                        Object.keys(req.trigger_context).length > 0 ? (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="text-sm text-foreground truncate block cursor-default">
                                  {req.reason}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent
                                side="bottom"
                                className="max-w-md bg-card border-border"
                              >
                                <pre className="text-[11px] text-dim font-mono whitespace-pre-wrap">
                                  {JSON.stringify(req.trigger_context, null, 2)}
                                </pre>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : (
                          <span className="text-sm text-foreground truncate block">
                            {req.reason}
                          </span>
                        )}
                      </TableCell>

                      {/* Confidence */}
                      <TableCell>
                        <span className="flex items-center gap-1 text-xs text-dim">
                          <Shield className="h-3 w-3" />
                          {(req.confidence * 100).toFixed(0)}%
                        </span>
                      </TableCell>

                      {/* Expires */}
                      <TableCell className="text-xs text-dim">
                        {shown === "expired" ? (
                          <span className="text-red-threat">Expired</span>
                        ) : (
                          formatDate(req.expires_at)
                        )}
                      </TableCell>

                      {/* Actions */}
                      <TableCell>
                        {actionable && (
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() =>
                                approve.mutate(
                                  { uuid: req.uuid },
                                  {
                                    onSuccess: () =>
                                      toast.success("Workflow approved"),
                                    onError: () =>
                                      toast.error("Failed to approve"),
                                  },
                                )
                              }
                              disabled={approve.isPending}
                              className="bg-teal text-white hover:bg-teal-dim h-7 text-xs"
                            >
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setRejectTarget(req.uuid)}
                              disabled={reject.isPending}
                              className="border-red-threat/30 text-red-threat hover:bg-red-threat/10 h-7 text-xs"
                            >
                              <XCircle className="h-3 w-3 mr-1" />
                              Reject
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
            {!isLoading && approvals.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="text-center text-sm text-dim py-20"
                >
                  No approval requests
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
        open={!!rejectTarget}
        onOpenChange={(v) => !v && setRejectTarget(null)}
        title="Reject Workflow"
        description="Are you sure you want to reject this workflow execution request?"
        confirmLabel="Reject"
        onConfirm={() => {
          if (rejectTarget) {
            reject.mutate(
              { uuid: rejectTarget },
              {
                onSuccess: () => {
                  toast.success("Workflow rejected");
                  setRejectTarget(null);
                },
                onError: () => toast.error("Failed to reject"),
              },
            );
          }
        }}
      />
    </AppLayout>
  );
}
