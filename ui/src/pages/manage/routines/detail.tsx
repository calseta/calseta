import { useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DetailPageHeader,
  DetailPageField,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
} from "@/components/detail-page";
import {
  useRoutine,
  useRoutineRuns,
  usePatchRoutine,
  usePatchTrigger,
  useTriggerRoutine,
  useDeleteRoutine,
} from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Play, Pause, RotateCcw, Trash2, Pencil } from "lucide-react";
import type { RoutineRun } from "@/lib/types";

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

function runStatusColor(status: string): string {
  switch (status) {
    case "completed":
      return "text-teal bg-teal/10 border-teal/30";
    case "failed":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "running":
      return "text-amber bg-amber/10 border-amber/30";
    case "skipped":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function runDuration(run: RoutineRun): string {
  if (!run.completed_at) return "—";
  const startMs = new Date(run.created_at).getTime();
  const endMs = new Date(run.completed_at).getTime();
  const diffSec = Math.round((endMs - startMs) / 1000);
  if (diffSec < 60) return `${diffSec}s`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m`;
  return `${(diffSec / 3600).toFixed(1)}h`;
}

interface EditForm {
  name: string;
  description: string;
  concurrency_policy: string;
  max_consecutive_failures: string;
  cron_expression: string;
}

export function RoutineDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const navigate = useNavigate();
  const { data: routineResp, isLoading, refetch, isFetching } = useRoutine(uuid);
  const { data: runsResp, refetch: refetchRuns } = useRoutineRuns(uuid);
  const patchRoutine = usePatchRoutine();
  const patchTrigger = usePatchTrigger();
  const triggerRoutine = useTriggerRoutine();
  const deleteRoutine = useDeleteRoutine();

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editForm, setEditForm] = useState<EditForm | null>(null);

  const routine = routineResp?.data;
  const runs = runsResp?.data ?? [];

  if (isLoading) {
    return (
      <AppLayout title="Routine">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!routine) {
    return (
      <AppLayout title="Routine">
        <div className="text-center text-sm text-dim py-20">Routine not found</div>
      </AppLayout>
    );
  }

  function handleTogglePause() {
    if (!routine) return;
    const newStatus = routine.status === "active" ? "paused" : "active";
    patchRoutine.mutate(
      { uuid, body: { status: newStatus } },
      {
        onSuccess: () =>
          toast.success(`Routine ${newStatus === "active" ? "resumed" : "paused"}`),
        onError: () => toast.error("Failed to update routine"),
      },
    );
  }

  function handleTrigger() {
    triggerRoutine.mutate(
      { uuid },
      {
        onSuccess: () => {
          toast.success("Routine triggered");
          refetchRuns();
        },
        onError: () => toast.error("Failed to trigger routine"),
      },
    );
  }

  function handleDelete() {
    deleteRoutine.mutate(uuid, {
      onSuccess: () => {
        toast.success("Routine deleted");
        navigate({ to: "/routines" });
      },
      onError: () => toast.error("Failed to delete routine"),
    });
  }

  function openEditDialog() {
    if (!routine) return;
    const firstCronTrigger = routine.triggers.find((t) => t.kind === "cron");
    setEditForm({
      name: routine.name,
      description: routine.description ?? "",
      concurrency_policy: routine.concurrency_policy,
      max_consecutive_failures: String(routine.max_consecutive_failures),
      cron_expression: firstCronTrigger?.cron_expression ?? "",
    });
    setShowEditDialog(true);
  }

  async function handleEditSave() {
    if (!editForm || !routine) return;

    const routineBody: Record<string, unknown> = {
      name: editForm.name.trim() || routine.name,
      description: editForm.description.trim() || null,
      concurrency_policy: editForm.concurrency_policy,
      max_consecutive_failures: parseInt(editForm.max_consecutive_failures) || routine.max_consecutive_failures,
    };

    const firstCronTrigger = routine.triggers.find((t) => t.kind === "cron");
    const cronChanged =
      firstCronTrigger && editForm.cron_expression !== (firstCronTrigger.cron_expression ?? "");

    let hasError = false;

    await new Promise<void>((resolve) => {
      patchRoutine.mutate(
        { uuid, body: routineBody },
        {
          onSuccess: () => resolve(),
          onError: () => {
            toast.error("Failed to save routine");
            hasError = true;
            resolve();
          },
        },
      );
    });

    if (!hasError && cronChanged && firstCronTrigger) {
      await new Promise<void>((resolve) => {
        patchTrigger.mutate(
          {
            routineUuid: uuid,
            triggerUuid: String(firstCronTrigger.uuid),
            body: { cron_expression: editForm.cron_expression },
          },
          {
            onSuccess: () => resolve(),
            onError: () => {
              toast.error("Failed to update cron expression");
              resolve();
            },
          },
        );
      });
    }

    if (!hasError) {
      toast.success("Routine saved");
      setShowEditDialog(false);
      setEditForm(null);
    }
  }

  const isSaving = patchRoutine.isPending || patchTrigger.isPending;

  return (
    <AppLayout title={routine.name}>
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/routines"
          title={routine.name}
          badges={
            <Badge
              variant="outline"
              className={cn("text-[10px]", routineStatusColor(routine.status))}
            >
              {routine.status}
            </Badge>
          }
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTrigger}
                disabled={triggerRoutine.isPending}
                className="h-8 gap-1.5 text-xs"
              >
                <Play className="h-3 w-3" />
                Trigger
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTogglePause}
                disabled={patchRoutine.isPending}
                className="h-8 gap-1.5 text-xs"
              >
                {routine.status === "active" ? (
                  <>
                    <Pause className="h-3 w-3" />
                    Pause
                  </>
                ) : (
                  <>
                    <RotateCcw className="h-3 w-3" />
                    Resume
                  </>
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDeleteConfirm(true)}
                className="h-8 w-8 p-0 text-dim hover:text-red-threat"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </>
          }
          onRefresh={() => { refetch(); refetchRuns(); }}
          isRefreshing={isFetching}
        />

        <Tabs defaultValue="configuration">
          <TabsList>
            <TabsTrigger value="configuration">Configuration</TabsTrigger>
            <TabsTrigger value="runs">
              Run History
              {runs.length > 0 && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {runs.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          {/* Configuration tab */}
          <TabsContent value="configuration" className="mt-4">
            <div className="flex justify-end mb-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={openEditDialog}
                className="h-8 gap-1.5 text-xs text-dim hover:text-foreground"
              >
                <Pencil className="h-3 w-3" />
                Edit
              </Button>
            </div>

            <DetailPageLayout
              sidebar={
                <DetailPageSidebar>
                  <SidebarSection title="Settings">
                    <DetailPageField label="Status" value={routine.status} />
                    <DetailPageField label="Concurrency Policy" value={routine.concurrency_policy} />
                    <DetailPageField label="Catch-up Policy" value={routine.catch_up_policy} />
                    <DetailPageField
                      label="Max Consecutive Failures"
                      value={String(routine.max_consecutive_failures)}
                    />
                    <DetailPageField
                      label="Consecutive Failures"
                      value={
                        <span
                          className={cn(
                            "text-xs",
                            routine.consecutive_failures > 0 ? "text-red-threat" : "text-dim",
                          )}
                        >
                          {routine.consecutive_failures}
                        </span>
                      }
                    />
                    <DetailPageField
                      label="Agent Registration"
                      value={
                        routine.agent_registration_uuid ? (
                          <span className="font-mono text-[11px]">
                            {routine.agent_registration_uuid.slice(0, 8)}...
                          </span>
                        ) : (
                          "—"
                        )
                      }
                    />
                    <DetailPageField
                      label="Last Run"
                      value={routine.last_run_at ? relativeTime(routine.last_run_at) : "—"}
                    />
                    <DetailPageField
                      label="Next Run"
                      value={routine.next_run_at ? relativeTime(routine.next_run_at) : "—"}
                    />
                    <DetailPageField label="Created" value={formatDate(routine.created_at)} />
                    <DetailPageField label="Updated" value={formatDate(routine.updated_at)} />
                  </SidebarSection>
                </DetailPageSidebar>
              }
            >
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">About</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-foreground">
                    {routine.description ?? (
                      <span className="text-dim">No description provided.</span>
                    )}
                  </p>
                </CardContent>
              </Card>

              {routine.triggers.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium">Triggers</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                          <TableHead className="text-dim text-xs pl-6">Kind</TableHead>
                          <TableHead className="text-dim text-xs">Cron Expression</TableHead>
                          <TableHead className="text-dim text-xs">Timezone</TableHead>
                          <TableHead className="text-dim text-xs">Next Run</TableHead>
                          <TableHead className="text-dim text-xs">Active</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {routine.triggers.map((trigger) => (
                          <TableRow key={trigger.uuid} className="border-border">
                            <TableCell className="text-xs pl-6">{trigger.kind}</TableCell>
                            <TableCell className="text-xs font-mono text-dim">
                              {trigger.cron_expression ?? "—"}
                            </TableCell>
                            <TableCell className="text-xs text-dim">
                              {trigger.timezone ?? "UTC"}
                            </TableCell>
                            <TableCell className="text-xs text-dim whitespace-nowrap">
                              {trigger.next_run_at ? relativeTime(trigger.next_run_at) : "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={cn(
                                  "text-[10px]",
                                  trigger.is_active
                                    ? "text-teal bg-teal/10 border-teal/30"
                                    : "text-dim bg-dim/10 border-dim/30",
                                )}
                              >
                                {trigger.is_active ? "active" : "inactive"}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </DetailPageLayout>
          </TabsContent>

          {/* Run History tab */}
          <TabsContent value="runs" className="mt-4">
            {runs.length === 0 ? (
              <div className="text-center text-sm text-dim py-20">No runs yet</div>
            ) : (
              <div className="rounded-lg border border-border bg-card">
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-transparent">
                      <TableHead className="text-dim text-xs">Source</TableHead>
                      <TableHead className="text-dim text-xs">Status</TableHead>
                      <TableHead className="text-dim text-xs">Started</TableHead>
                      <TableHead className="text-dim text-xs">Duration</TableHead>
                      <TableHead className="text-dim text-xs">Error</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((run) => (
                      <TableRow key={run.uuid} className="border-border hover:bg-accent/50">
                        <TableCell className="text-xs text-muted-foreground">
                          {run.source}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn("text-[10px]", runStatusColor(run.status))}
                          >
                            {run.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-dim whitespace-nowrap">
                          {relativeTime(run.created_at)}
                        </TableCell>
                        <TableCell className="text-xs text-dim">
                          {runDuration(run)}
                        </TableCell>
                        <TableCell className="text-xs text-red-threat max-w-[240px] truncate">
                          {run.error ?? "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Edit dialog */}
      {editForm && (
        <Dialog open={showEditDialog} onOpenChange={(v) => { if (!v) { setShowEditDialog(false); setEditForm(null); } }}>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Routine</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label>Name</Label>
                <Input
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  rows={3}
                  placeholder="Describe what this routine does..."
                />
              </div>
              <div className="space-y-1.5">
                <Label>Concurrency Policy</Label>
                <Select
                  value={editForm.concurrency_policy}
                  onValueChange={(v) => setEditForm({ ...editForm, concurrency_policy: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip_if_active">skip_if_active</SelectItem>
                    <SelectItem value="coalesce_if_active">coalesce_if_active</SelectItem>
                    <SelectItem value="always_run">always_run</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Failure Threshold</Label>
                <Input
                  type="number"
                  min={1}
                  value={editForm.max_consecutive_failures}
                  onChange={(e) => setEditForm({ ...editForm, max_consecutive_failures: e.target.value })}
                />
              </div>
              {routine.triggers.some((t) => t.kind === "cron") && (
                <div className="space-y-1.5">
                  <Label>Cron Expression</Label>
                  <Input
                    value={editForm.cron_expression}
                    onChange={(e) => setEditForm({ ...editForm, cron_expression: e.target.value })}
                    placeholder="e.g. 0 * * * *"
                    className="font-mono"
                  />
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => { setShowEditDialog(false); setEditForm(null); }}
                disabled={isSaving}
              >
                Cancel
              </Button>
              <Button
                onClick={handleEditSave}
                disabled={isSaving}
                className="bg-teal text-white hover:bg-teal-dim"
              >
                {isSaving ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Routine</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <span className="text-foreground font-medium">{routine.name}</span>?
            This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteRoutine.isPending}
            >
              {deleteRoutine.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
