import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useApprovals,
  useApproveWorkflow,
  useRejectWorkflow,
} from "@/hooks/use-api";
import { relativeTime, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, Clock, Shield } from "lucide-react";
import { useState } from "react";

export function ApprovalsPage() {
  const { data, isLoading } = useApprovals();
  const approve = useApproveWorkflow();
  const reject = useRejectWorkflow();
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);

  const approvals = data?.data ?? [];

  if (isLoading) {
    return (
      <AppLayout title="Workflow Approvals">
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Workflow Approvals">
      <div className="space-y-3">
        {approvals.length === 0 && (
          <div className="text-center text-sm text-dim py-20">
            No approval requests
          </div>
        )}
        {approvals.map((req) => (
          <Card key={req.uuid} className="bg-card border-border hover:border-teal/30 transition-colors">
            <CardContent className="p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <StatusIcon status={req.status} />
                    {req.workflow_name && (
                      <span className="text-sm font-medium text-foreground">
                        {req.workflow_name}
                      </span>
                    )}
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[11px]",
                        req.status === "pending"
                          ? "text-amber bg-amber/10 border-amber/30"
                          : req.status === "approved"
                            ? "text-teal bg-teal/10 border-teal/30"
                            : "text-red-threat bg-red-threat/10 border-red-threat/30",
                      )}
                    >
                      {req.status}
                    </Badge>
                    <span className="text-xs text-dim">
                      via {req.notifier_type}
                    </span>
                  </div>
                  <p className="text-sm text-foreground">{req.reason}</p>
                  <div className="flex gap-4 text-xs text-dim">
                    <span className="flex items-center gap-1">
                      <Shield className="h-3 w-3" />
                      Confidence: {(req.confidence * 100).toFixed(0)}%
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Expires: {formatDate(req.expires_at)}
                    </span>
                    <span>{relativeTime(req.created_at)}</span>
                  </div>
                  {req.trigger_context && (
                    <pre className="mt-1 text-[11px] text-dim font-mono">
                      {JSON.stringify(req.trigger_context, null, 2)}
                    </pre>
                  )}
                </div>

                {req.status === "pending" && (
                  <div className="flex gap-2 shrink-0">
                    <Button
                      size="sm"
                      onClick={() =>
                        approve.mutate({ uuid: req.uuid }, {
                          onSuccess: () => toast.success("Workflow approved"),
                          onError: () => toast.error("Failed to approve"),
                        })
                      }
                      disabled={approve.isPending}
                      className="bg-teal text-white hover:bg-teal-dim"
                    >
                      <CheckCircle className="h-3.5 w-3.5 mr-1" />
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setRejectTarget(req.uuid)}
                      disabled={reject.isPending}
                      className="border-red-threat/30 text-red-threat hover:bg-red-threat/10"
                    >
                      <XCircle className="h-3.5 w-3.5 mr-1" />
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={!!rejectTarget}
        onOpenChange={(v) => !v && setRejectTarget(null)}
        title="Reject Workflow"
        description="Are you sure you want to reject this workflow execution request?"
        confirmLabel="Reject"
        onConfirm={() => {
          if (rejectTarget) {
            reject.mutate({ uuid: rejectTarget }, {
              onSuccess: () => {
                toast.success("Workflow rejected");
                setRejectTarget(null);
              },
              onError: () => toast.error("Failed to reject"),
            });
          }
        }}
      />
    </AppLayout>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "approved") return <CheckCircle className="h-4 w-4 text-teal" />;
  if (status === "rejected" || status === "expired")
    return <XCircle className="h-4 w-4 text-red-threat" />;
  return <Clock className="h-4 w-4 text-amber" />;
}
