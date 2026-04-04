import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useRoutines,
  useCreateRoutine,
  usePatchRoutine,
  useTriggerRoutine,
} from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw, Plus, Play, Pause, RotateCcw } from "lucide-react";

const CONCURRENCY_POLICIES = ["allow", "skip", "replace", "queue"];

function routineStatusColor(status: string): string {
  switch (status) {
    case "active":
      return "text-teal bg-teal/10 border-teal/30";
    case "paused":
      return "text-amber bg-amber/10 border-amber/30";
    case "completed":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

export function RoutinesPage() {
  const [showNewRoutine, setShowNewRoutine] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formAgentUuid, setFormAgentUuid] = useState("");
  const [formConcurrencyPolicy, setFormConcurrencyPolicy] = useState<string>("");

  const { data, isLoading, refetch, isFetching } = useRoutines({ page_size: 100 });
  const createRoutine = useCreateRoutine();
  const patchRoutine = usePatchRoutine();
  const triggerRoutine = useTriggerRoutine();

  const routines = data?.data ?? [];

  function handleCreate() {
    if (!formName.trim()) {
      toast.error("Name is required");
      return;
    }
    const body: Record<string, unknown> = {
      name: formName.trim(),
    };
    if (formDescription.trim()) body.description = formDescription.trim();
    if (formAgentUuid.trim()) body.agent_registration_uuid = formAgentUuid.trim();
    if (formConcurrencyPolicy) body.concurrency_policy = formConcurrencyPolicy;

    createRoutine.mutate(body, {
      onSuccess: () => {
        toast.success("Routine created");
        setShowNewRoutine(false);
        setFormName("");
        setFormDescription("");
        setFormAgentUuid("");
        setFormConcurrencyPolicy("");
      },
      onError: () => toast.error("Failed to create routine"),
    });
  }

  function handleTogglePause(uuid: string, currentStatus: string) {
    const newStatus = currentStatus === "active" ? "paused" : "active";
    patchRoutine.mutate(
      { uuid, body: { status: newStatus } },
      {
        onSuccess: () => toast.success(`Routine ${newStatus === "active" ? "resumed" : "paused"}`),
        onError: () => toast.error("Failed to update routine"),
      },
    );
  }

  function handleTrigger(uuid: string) {
    triggerRoutine.mutate(
      { uuid },
      {
        onSuccess: () => toast.success("Routine triggered"),
        onError: () => toast.error("Failed to trigger routine"),
      },
    );
  }

  return (
    <AppLayout title="Routines">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
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
            {data?.meta && (
              <span className="text-xs text-dim">
                {data.meta.total} routine{data.meta.total !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <Button size="sm" onClick={() => setShowNewRoutine(true)} className="h-8 gap-1">
            <Plus className="h-3.5 w-3.5" />
            New Routine
          </Button>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Name</TableHead>
                <TableHead className="text-dim text-xs">Trigger</TableHead>
                <TableHead className="text-dim text-xs">Schedule</TableHead>
                <TableHead className="text-dim text-xs">Status</TableHead>
                <TableHead className="text-dim text-xs">Failures</TableHead>
                <TableHead className="text-dim text-xs">Last Run</TableHead>
                <TableHead className="text-dim text-xs">Next Run</TableHead>
                <TableHead className="text-dim text-xs w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-8" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    </TableRow>
                  ))
                : routines.map((routine) => {
                    const firstTrigger = routine.triggers[0];
                    return (
                      <TableRow
                        key={routine.uuid}
                        className="border-border hover:bg-accent/50"
                      >
                        <TableCell>
                          <Link
                            to="/manage/routines/$uuid"
                            params={{ uuid: routine.uuid }}
                            search={{ tab: "configuration" }}
                            className="text-sm text-foreground hover:text-teal-light transition-colors font-medium"
                          >
                            {routine.name}
                          </Link>
                          {routine.description && (
                            <p className="text-[11px] text-dim mt-0.5 truncate max-w-[200px]">
                              {routine.description}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {firstTrigger?.kind ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs font-mono text-dim">
                          {firstTrigger?.cron_expression ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn("text-[10px]", routineStatusColor(routine.status))}
                          >
                            {routine.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {routine.consecutive_failures > 0 ? (
                            <span className="text-xs text-red-threat font-medium">
                              {routine.consecutive_failures}
                            </span>
                          ) : (
                            <span className="text-xs text-dim">0</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-dim whitespace-nowrap">
                          {routine.last_run_at ? relativeTime(routine.last_run_at) : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-dim whitespace-nowrap">
                          {routine.next_run_at ? relativeTime(routine.next_run_at) : "—"}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Trigger now"
                              onClick={() => handleTrigger(routine.uuid)}
                              className="h-7 w-7 p-0 text-dim hover:text-teal"
                            >
                              <Play className="h-3 w-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              title={routine.status === "active" ? "Pause" : "Resume"}
                              onClick={() => handleTogglePause(routine.uuid, routine.status)}
                              className="h-7 w-7 p-0 text-dim hover:text-amber"
                            >
                              {routine.status === "active" ? (
                                <Pause className="h-3 w-3" />
                              ) : (
                                <RotateCcw className="h-3 w-3" />
                              )}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
              {!isLoading && routines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8}>
                    <div className="text-center text-sm text-dim py-20">
                      No routines configured
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* New Routine Dialog */}
      <Dialog open={showNewRoutine} onOpenChange={setShowNewRoutine}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Routine</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="routine-name">Name *</Label>
              <Input
                id="routine-name"
                placeholder="Routine name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="routine-description">Description</Label>
              <Textarea
                id="routine-description"
                placeholder="What does this routine do?"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={2}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="routine-agent">Agent Registration UUID</Label>
              <Input
                id="routine-agent"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={formAgentUuid}
                onChange={(e) => setFormAgentUuid(e.target.value)}
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Concurrency Policy</Label>
              <Select value={formConcurrencyPolicy} onValueChange={setFormConcurrencyPolicy}>
                <SelectTrigger>
                  <SelectValue placeholder="Select policy" />
                </SelectTrigger>
                <SelectContent>
                  {CONCURRENCY_POLICIES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewRoutine(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createRoutine.isPending}>
              {createRoutine.isPending ? "Creating..." : "Create Routine"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
