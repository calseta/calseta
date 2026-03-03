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
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflows, useCreateWorkflow } from "@/hooks/use-api";
import { relativeTime, riskColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ShieldCheck, Code, Lock, Plus, RefreshCw } from "lucide-react";

const WORKFLOW_TEMPLATE = `async def run(ctx):
    """
    Workflow entry point.

    ctx provides: indicator, alert, http, log, secrets, integrations
    Returns: WorkflowResult.success(...) or WorkflowResult.fail(...)
    """
    ctx.log.info("Starting workflow")

    # Your workflow logic here

    return ctx.result.success(
        message="Workflow completed",
        data={}
    )
`;

export function WorkflowsListPage() {
  const { data, isLoading, refetch, isFetching } = useWorkflows({ page_size: 50 });
  const createWorkflow = useCreateWorkflow();
  const workflows = data?.data ?? [];

  const [open, setOpen] = useState(false);
  const [riskLevel, setRiskLevel] = useState("low");
  const [requiresApproval, setRequiresApproval] = useState(false);

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    createWorkflow.mutate(
      {
        name: fd.get("name") as string,
        workflow_type: (fd.get("workflow_type") as string) || null,
        risk_level: riskLevel,
        requires_approval: requiresApproval,
        code: fd.get("code") as string,
        documentation: (fd.get("documentation") as string) || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setRiskLevel("low");
          setRequiresApproval(false);
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
            <span className="text-xs text-dim">
              {data?.meta?.total ?? 0} workflows
            </span>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Create Workflow
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-2xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Workflow</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-muted-foreground">Name</Label>
                    <Input name="name" required className="mt-1 bg-surface border-border text-sm" placeholder="e.g. block-malicious-ip" />
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Type</Label>
                    <Input name="workflow_type" className="mt-1 bg-surface border-border text-sm" placeholder="e.g. enrichment, containment, response" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-muted-foreground">Risk Level</Label>
                    <Select value={riskLevel} onValueChange={setRiskLevel}>
                      <SelectTrigger className="mt-1 bg-surface border-border text-sm">
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
                  <div className="flex items-end pb-1">
                    <div className="flex items-center gap-2">
                      <Switch checked={requiresApproval} onCheckedChange={setRequiresApproval} />
                      <Label className="text-xs text-muted-foreground">Requires Approval</Label>
                    </div>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Documentation</Label>
                  <Textarea name="documentation" className="mt-1 bg-surface border-border text-sm" rows={2} placeholder="What does this workflow do?" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Code</Label>
                  <Textarea
                    name="code"
                    required
                    rows={14}
                    className="mt-1 bg-surface border-border text-sm font-mono"
                    defaultValue={WORKFLOW_TEMPLATE}
                  />
                </div>
                <Button type="submit" disabled={createWorkflow.isPending} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Name</TableHead>
                <TableHead className="text-dim text-xs">State</TableHead>
                <TableHead className="text-dim text-xs">Type</TableHead>
                <TableHead className="text-dim text-xs">Risk</TableHead>
                <TableHead className="text-dim text-xs">Approval</TableHead>
                <TableHead className="text-dim text-xs">Version</TableHead>
                <TableHead className="text-dim text-xs">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
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
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", riskColor(wf.risk_level))}
                        >
                          {wf.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {wf.requires_approval ? (
                          <Lock className="h-3.5 w-3.5 text-amber" />
                        ) : (
                          <span className="text-xs text-dim">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-dim font-mono">
                        v{wf.code_version}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {relativeTime(wf.updated_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && workflows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No workflows configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </AppLayout>
  );
}
