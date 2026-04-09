import { useState, useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  DndContext,
  DragOverlay,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { useIssues, useCreateIssue, usePatchIssue } from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw, Plus } from "lucide-react";
import type { AgentIssue } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  remediation: "Remediation",
  detection_tuning: "Detection Tuning",
  investigation: "Investigation",
  compliance: "Compliance",
  post_incident: "Post Incident",
  maintenance: "Maintenance",
  custom: "Custom",
};

const CATEGORIES = Object.keys(CATEGORY_LABELS);
const PRIORITIES = ["critical", "high", "medium", "low"];

const KANBAN_COLUMNS = [
  { key: "open", label: "Open", statuses: ["backlog", "todo"], dropStatus: "todo", borderColor: "border-teal/50" },
  { key: "in_progress", label: "In Progress", statuses: ["in_progress", "in_review"], dropStatus: "in_progress", borderColor: "border-amber/50" },
  { key: "done", label: "Done", statuses: ["done"], dropStatus: "done", borderColor: "border-teal/50" },
  { key: "blocked", label: "Blocked", statuses: ["blocked", "cancelled"], dropStatus: "blocked", borderColor: "border-red-threat/50" },
] as const;

type ColumnKey = typeof KANBAN_COLUMNS[number]["key"];

function priorityColor(priority: string): string {
  switch (priority) {
    case "critical":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "high":
      return "text-amber bg-amber/10 border-amber/30";
    case "medium":
      return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "low":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function issueStatusColor(status: string): string {
  switch (status) {
    case "in_progress":
    case "in_review":
      return "text-amber bg-amber/10 border-amber/30";
    case "done":
      return "text-teal bg-teal/10 border-teal/30";
    case "blocked":
    case "cancelled":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default:
      return "text-dim bg-dim/10 border-dim/30";
  }
}

// Static card used inside DragOverlay (no drag hooks)
function KanbanCardStatic({ issue }: { issue: AgentIssue }) {
  return (
    <div className="bg-card border border-border rounded-md shadow-xl rotate-1 p-3 space-y-2 w-[264px] opacity-95">
      <p className="text-sm font-semibold text-foreground leading-snug line-clamp-1">
        {issue.title}
      </p>
      {issue.description && (
        <p className="text-xs text-dim leading-snug line-clamp-2">{issue.description}</p>
      )}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">
            {issue.identifier}
          </Badge>
          {issue.priority && (
            <Badge variant="outline" className={cn("text-[10px]", priorityColor(issue.priority))}>
              {issue.priority}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {(issue.assignee_operator ?? issue.assignee_agent_uuid) && (
            <span className="text-[10px] text-dim truncate max-w-[80px]">
              {issue.assignee_operator ?? issue.assignee_agent_uuid}
            </span>
          )}
          <span className="text-[10px] text-dim">{relativeTime(issue.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

// Sortable card with drag handle behavior
function KanbanCard({ issue, isDragging }: { issue: AgentIssue; isDragging: boolean }) {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id: issue.uuid,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        "bg-card border border-border rounded-md shadow-sm transition-shadow p-3 space-y-2",
        "cursor-grab active:cursor-grabbing",
        isDragging ? "opacity-40" : "hover:shadow-md",
      )}
      onClick={() => {
        if (isDragging) return;
        navigate({ to: "/manage/issues/$uuid", params: { uuid: issue.uuid }, search: { tab: "details" } });
      }}
    >
      <p className="text-sm font-semibold text-foreground leading-snug line-clamp-1">
        {issue.title}
      </p>
      {issue.description && (
        <p className="text-xs text-dim leading-snug line-clamp-2">{issue.description}</p>
      )}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">
            {issue.identifier}
          </Badge>
          {issue.priority && (
            <Badge variant="outline" className={cn("text-[10px]", priorityColor(issue.priority))}>
              {issue.priority}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {(issue.assignee_operator ?? issue.assignee_agent_uuid) && (
            <span className="text-[10px] text-dim truncate max-w-[80px]">
              {issue.assignee_operator ?? issue.assignee_agent_uuid}
            </span>
          )}
          <span className="text-[10px] text-dim">{relativeTime(issue.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

function KanbanColumn({
  colKey,
  label,
  issues,
  borderColor,
  activeId,
  isOver,
}: {
  colKey: string;
  label: string;
  issues: AgentIssue[];
  borderColor: string;
  activeId: string | null;
  isOver: boolean;
}) {
  const { setNodeRef } = useDroppable({ id: colKey });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "shrink-0 w-[280px] flex flex-col rounded-lg border bg-muted/5 transition-colors",
        isOver ? cn("border-2", borderColor) : "border-border",
      )}
    >
      {/* Column header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <span className="text-[10px] bg-muted text-dim px-1.5 py-0.5 rounded-full">
          {issues.length}
        </span>
      </div>
      {/* Scrollable card list */}
      <SortableContext items={issues.map((i) => i.uuid)} strategy={verticalListSortingStrategy}>
        <div className="flex flex-col gap-2 p-2 overflow-y-auto max-h-[calc(100vh-260px)]">
          {issues.length === 0 ? (
            <div className="text-center text-xs text-dim py-8">No issues</div>
          ) : (
            issues.map((issue) => (
              <KanbanCard key={issue.uuid} issue={issue} isDragging={activeId === issue.uuid} />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
}

function IssueCardSkeleton() {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-16" />
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-3 w-24" />
      </CardContent>
    </Card>
  );
}

export function IssuesPage() {
  const [showNewIssue, setShowNewIssue] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  // Optimistic local overrides: uuid -> status
  const [localStatusMap, setLocalStatusMap] = useState<Record<string, string>>({});

  // Form state
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState<string>("");
  const [formPriority, setFormPriority] = useState<string>("");

  const { data, isLoading, refetch, isFetching } = useIssues({ page_size: 200 });
  const createIssue = useCreateIssue();
  const patchIssue = usePatchIssue();

  const rawIssues = data?.data ?? [];

  // Apply local optimistic overrides on top of API data
  const issues: AgentIssue[] = rawIssues.map((issue) =>
    localStatusMap[issue.uuid] !== undefined
      ? { ...issue, status: localStatusMap[issue.uuid] }
      : issue,
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const activeIssue = activeId ? issues.find((i) => i.uuid === activeId) ?? null : null;

  // Determine which column key an issue belongs to (with local override applied)
  function getColumnForStatus(status: string): ColumnKey | null {
    for (const col of KANBAN_COLUMNS) {
      if ((col.statuses as readonly string[]).includes(status)) return col.key;
    }
    return null;
  }

  function filterIssuesByColumn(colKey: ColumnKey): AgentIssue[] {
    return issues.filter((i) => getColumnForStatus(i.status) === colKey);
  }

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(String(event.active.id));
  }, []);

  const handleDragOver = useCallback((event: { over: { id: string } | null }) => {
    setOverId(event.over ? String(event.over.id) : null);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveId(null);
      setOverId(null);

      if (!over) return;

      const draggedUuid = String(active.id);
      const overId = String(over.id);

      // Determine target column: could be a column key or another card's uuid
      let targetCol = KANBAN_COLUMNS.find((c) => c.key === overId) ?? null;
      if (!targetCol) {
        // over is a card uuid — find its column
        const overIssue = issues.find((i) => i.uuid === overId);
        if (overIssue) {
          const colKey = getColumnForStatus(overIssue.status);
          targetCol = KANBAN_COLUMNS.find((c) => c.key === colKey) ?? null;
        }
      }

      if (!targetCol) return;

      const draggedIssue = issues.find((i) => i.uuid === draggedUuid);
      if (!draggedIssue) return;

      const currentColKey = getColumnForStatus(draggedIssue.status);
      if (currentColKey === targetCol.key) return; // no-op, same column

      const newStatus = targetCol.dropStatus;
      const prevStatus = draggedIssue.status;

      // Optimistic update
      setLocalStatusMap((prev) => ({ ...prev, [draggedUuid]: newStatus }));

      patchIssue.mutate(
        { uuid: draggedUuid, body: { status: newStatus } },
        {
          onSuccess: () => {
            // Clear local override — API data will take over after invalidation
            setLocalStatusMap((prev) => {
              const next = { ...prev };
              delete next[draggedUuid];
              return next;
            });
          },
          onError: () => {
            // Revert optimistic update
            setLocalStatusMap((prev) => ({ ...prev, [draggedUuid]: prevStatus }));
            toast.error("Failed to move issue");
          },
        },
      );
    },
    [issues, patchIssue],
  );

  function handleCreateIssue() {
    if (!formTitle.trim()) {
      toast.error("Title is required");
      return;
    }
    const body: Record<string, unknown> = {
      title: formTitle.trim(),
    };
    if (formDescription.trim()) body.description = formDescription.trim();
    if (formCategory) body.category = formCategory;
    if (formPriority) body.priority = formPriority;

    createIssue.mutate(body, {
      onSuccess: () => {
        toast.success("Issue created");
        setShowNewIssue(false);
        setFormTitle("");
        setFormDescription("");
        setFormCategory("");
        setFormPriority("");
      },
      onError: () => toast.error("Failed to create issue"),
    });
  }

  return (
    <AppLayout title="Issues">
      <div className="space-y-4">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="h-8 w-8 p-0 text-dim hover:text-teal"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          </Button>

          <Button size="sm" onClick={() => setShowNewIssue(true)} className="h-8 gap-1">
            <Plus className="h-3.5 w-3.5" />
            New Issue
          </Button>
        </div>

        {/* Kanban board */}
        {isLoading ? (
          <div className="flex gap-4 overflow-x-auto pb-2">
            {Array.from({ length: 4 }).map((_, ci) => (
              <div key={ci} className="shrink-0 w-[280px] bg-muted/5 rounded-lg border border-border p-3 space-y-3">
                <Skeleton className="h-5 w-24" />
                {Array.from({ length: 3 }).map((_, i) => (
                  <IssueCardSkeleton key={i} />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
          >
            <div className="flex gap-4 overflow-x-auto pb-2 items-start">
              {KANBAN_COLUMNS.map((col) => (
                <KanbanColumn
                  key={col.key}
                  colKey={col.key}
                  label={col.label}
                  issues={filterIssuesByColumn(col.key)}
                  borderColor={col.borderColor}
                  activeId={activeId}
                  isOver={overId === col.key}
                />
              ))}
            </div>
            <DragOverlay>
              {activeIssue ? <KanbanCardStatic issue={activeIssue} /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>

      {/* New Issue Dialog */}
      <Dialog open={showNewIssue} onOpenChange={setShowNewIssue}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Issue</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="issue-title">Title *</Label>
              <Input
                id="issue-title"
                placeholder="Issue title"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="issue-description">Description</Label>
              <Textarea
                id="issue-description"
                placeholder="Describe the issue..."
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Category</Label>
                <Select value={formCategory} onValueChange={setFormCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {CATEGORY_LABELS[cat]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Priority</Label>
                <Select value={formPriority} onValueChange={setFormPriority}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select priority" />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p.charAt(0).toUpperCase() + p.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewIssue(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateIssue} disabled={createIssue.isPending}>
              {createIssue.isPending ? "Creating..." : "Create Issue"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
