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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useAgents, useCreateAgent, useDeleteAgent } from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { CopyableText } from "@/components/copyable-text";
import { Plus, Trash2, Bot, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export function AgentsPage() {
  const { data, isLoading, refetch, isFetching } = useAgents();
  const createAgent = useCreateAgent();
  const deleteAgent = useDeleteAgent();
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);

  const agents = data?.data ?? [];

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const description = (fd.get("description") as string)?.trim() || undefined;
    createAgent.mutate(
      {
        name: fd.get("name") as string,
        endpoint_url: fd.get("endpoint_url") as string,
        description,
        is_active: true,
        trigger_on_sources: [],
        trigger_on_severities: [],
      },
      {
        onSuccess: () => {
          setOpen(false);
          toast.success("Agent registered");
        },
        onError: () => toast.error("Failed to register agent"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteAgent.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Agent deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete agent"),
    });
  }

  return (
    <AppLayout title="Agent Registrations">
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
            <span className="text-xs text-dim">{agents.length} agents</span>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Register Agent
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border">
              <DialogHeader>
                <DialogTitle>Register Agent</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">Name</Label>
                  <Input name="name" required className="mt-1 bg-surface border-border text-sm" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Endpoint URL</Label>
                  <Input name="endpoint_url" required type="url" className="mt-1 bg-surface border-border text-sm" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Description (optional)</Label>
                  <Textarea
                    name="description"
                    rows={2}
                    className="mt-1 bg-surface border-border text-sm"
                    placeholder="What does this agent do?"
                  />
                </div>
                <Button type="submit" disabled={createAgent.isPending} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Register
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Agent</TableHead>
                <TableHead className="text-dim text-xs">UUID</TableHead>
                <TableHead className="text-dim text-xs">Endpoint URL</TableHead>
                <TableHead className="text-dim text-xs">Status</TableHead>
                <TableHead className="text-dim text-xs">Triggers</TableHead>
                <TableHead className="text-dim text-xs">Registered</TableHead>
                <TableHead className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : agents.map((agent) => (
                    <TableRow key={agent.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          to={`/settings/agents/${agent.uuid}`}
                          className="flex items-center gap-2 hover:text-teal transition-colors"
                        >
                          <Bot className="h-3.5 w-3.5 text-teal" />
                          <span className="text-sm text-foreground hover:text-teal">{agent.name}</span>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <CopyableText text={agent.uuid} mono className="text-[11px] text-dim" />
                      </TableCell>
                      <TableCell>
                        <CopyableText text={agent.endpoint_url} mono className="text-[11px] text-dim max-w-48 truncate" />
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={agent.is_active ? "text-teal bg-teal/10 border-teal/30 text-[11px]" : "text-dim bg-dim/10 border-dim/30 text-[11px]"}>
                          {agent.is_active ? "active" : "inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {[
                          ...agent.trigger_on_severities.map((s) => `sev:${s}`),
                          ...agent.trigger_on_sources.map((s) => `src:${s}`),
                        ].join(", ") || "all"}
                      </TableCell>
                      <TableCell className="text-xs text-dim">{relativeTime(agent.created_at)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget({ uuid: agent.uuid, name: agent.name })}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && agents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No agents registered
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Agent"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
