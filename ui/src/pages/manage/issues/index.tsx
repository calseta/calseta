import { useState, useCallback, useEffect, useRef } from "react";
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
import { ConfirmDialog } from "@/components/confirm-dialog";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useIssues,
  useCreateIssue,
  usePatchIssue,
  useAgents,
  useLabels,
  useIssueCategories,
  useCreateIssueCategory,
  useDeleteIssueCategory,
  usePatchIssueCategory,
} from "@/hooks/use-api";
import { relativeTime, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw, Plus, LayoutList, Columns, Search, X, Settings2, Trash2, Pencil, Check } from "lucide-react";
import type { AgentIssue, IssueCategoryDef } from "@/lib/types";

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const PRIORITIES = ["critical", "high", "medium", "low"];
const STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"];

const KANBAN_COLUMNS = [
  { key: "open", label: "Backlog", statuses: ["backlog", "todo"], dropStatus: "todo", borderColor: "border-teal/50" },
  { key: "in_progress", label: "In Progress", statuses: ["in_progress", "in_review"], dropStatus: "in_progress", borderColor: "border-amber/50" },
  { key: "blocked", label: "Blocked", statuses: ["blocked"], dropStatus: "blocked", borderColor: "border-red-threat/50" },
  { key: "done", label: "Done", statuses: ["done", "cancelled"], dropStatus: "done", borderColor: "border-teal/50" },
] as const;

type ColumnKey = typeof KANBAN_COLUMNS[number]["key"];

function priorityColor(priority: string): string {
  switch (priority) {
    case "critical": return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "high": return "text-amber bg-amber/10 border-amber/30";
    case "medium": return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "low": return "text-dim bg-dim/10 border-dim/30";
    default: return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function statusColor(status: string): string {
  switch (status) {
    case "in_progress":
    case "in_review": return "text-amber bg-amber/10 border-amber/30";
    case "done": return "text-teal bg-teal/10 border-teal/30";
    case "blocked":
    case "cancelled": return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "todo": return "text-blue-400 bg-blue-400/10 border-blue-400/30";
    default: return "text-dim bg-dim/10 border-dim/30";
  }
}

function priorityDot(priority: string): string {
  switch (priority) {
    case "critical": return "bg-red-threat";
    case "high": return "bg-amber";
    case "medium": return "bg-teal-light";
    case "low": return "bg-dim";
    default: return "bg-muted-foreground";
  }
}

// ─── Kanban Components ───────────────────────────────────────────────────────

function KanbanCardStatic({ issue }: { issue: AgentIssue }) {
  return (
    <div className="surface-2 border border-border rounded-md shadow-xl rotate-1 p-3 space-y-2 w-[264px] opacity-95">
      <div className="flex items-center gap-1.5">
        <div className={cn("h-2 w-2 rounded-full shrink-0", priorityDot(issue.priority))} />
        <p className="text-sm font-medium text-foreground leading-snug line-clamp-1">{issue.title}</p>
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">{issue.identifier}</Badge>
        <Badge variant="outline" className={cn("text-[10px]", statusColor(issue.status))}>{formatStatus(issue.status)}</Badge>
      </div>
    </div>
  );
}

function KanbanCard({ issue, isDragging }: { issue: AgentIssue; isDragging: boolean }) {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: issue.uuid });
  const style = { transform: CSS.Transform.toString(transform), transition };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        "surface-2 border border-border rounded-md shadow-sm transition-shadow p-3 space-y-2",
        "cursor-grab active:cursor-grabbing",
        isDragging ? "opacity-40" : "hover:shadow-md",
      )}
      onClick={() => {
        if (isDragging) return;
        navigate({ to: "/issues/$uuid", params: { uuid: issue.uuid }, search: { tab: "details" } });
      }}
    >
      <div className="flex items-start gap-1.5">
        <div className={cn("h-2 w-2 rounded-full shrink-0 mt-1", priorityDot(issue.priority))} />
        <p className="text-sm font-medium text-foreground leading-snug line-clamp-2">{issue.title}</p>
      </div>
      {issue.description && (
        <p className="text-xs text-dim leading-snug line-clamp-2 pl-3.5">{issue.description}</p>
      )}
      <div className="flex items-center justify-between gap-2 pl-0.5">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">{issue.identifier}</Badge>
          {issue.priority && (
            <Badge variant="outline" className={cn("text-[10px]", priorityColor(issue.priority))}>{issue.priority.charAt(0).toUpperCase() + issue.priority.slice(1)}</Badge>
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
        "shrink-0 w-[280px] flex flex-col rounded-lg border surface-1 transition-colors h-full",
        isOver ? cn("border-2", borderColor) : "border-border",
      )}
    >
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border shrink-0">
        <span className="micro-label text-foreground">{label}</span>
        <span className="text-[10px] bg-muted text-dim px-1.5 py-0.5 rounded-full">{issues.length}</span>
      </div>
      <SortableContext items={issues.map((i) => i.uuid)} strategy={verticalListSortingStrategy}>
        <div className="flex flex-col gap-2 p-2 flex-1 overflow-y-auto min-h-0">
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

// ─── List View ───────────────────────────────────────────────────────────────

function ListView({ issues, categoryMap }: { issues: AgentIssue[]; categoryMap: Record<string, string> }) {
  const navigate = useNavigate();

  if (issues.length === 0) {
    return (
      <div className="text-center py-20 text-sm text-dim">No issues match your filters</div>
    );
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="micro-label w-20">ID</TableHead>
            <TableHead className="micro-label">Title</TableHead>
            <TableHead className="micro-label w-28">Status</TableHead>
            <TableHead className="micro-label w-24">Priority</TableHead>
            <TableHead className="micro-label w-28">Category</TableHead>
            <TableHead className="micro-label w-28">Assignee</TableHead>
            <TableHead className="micro-label w-28">Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {issues.map((issue) => (
            <TableRow
              key={issue.uuid}
              className="cursor-pointer hover:bg-muted/20 transition-colors"
              onClick={() => navigate({ to: "/issues/$uuid", params: { uuid: issue.uuid }, search: { tab: "details" } })}
            >
              <TableCell>
                <span className="text-[11px] font-mono text-dim">{issue.identifier}</span>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <div className={cn("h-2 w-2 rounded-full shrink-0", priorityDot(issue.priority))} />
                  <span className="text-sm font-medium text-foreground line-clamp-1">{issue.title}</span>
                </div>
              </TableCell>
              <TableCell>
                <Badge variant="outline" className={cn("text-[10px]", statusColor(issue.status))}>
                  {formatStatus(issue.status)}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant="outline" className={cn("text-[10px]", priorityColor(issue.priority))}>
                  {issue.priority.charAt(0).toUpperCase() + issue.priority.slice(1)}
                </Badge>
              </TableCell>
              <TableCell>
                <span className="text-xs text-dim">{categoryMap[issue.category] ?? issue.category ?? "—"}</span>
              </TableCell>
              <TableCell>
                <span className="text-xs text-dim truncate block max-w-[100px]">
                  {issue.assignee_operator ?? issue.assignee_agent_uuid ?? "—"}
                </span>
              </TableCell>
              <TableCell>
                <span className="text-xs text-dim">{formatDate(issue.created_at)}</span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── New Issue Dialog ────────────────────────────────────────────────────────

function NewIssueDialog({
  open,
  onOpenChange,
  categories,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: IssueCategoryDef[];
}) {
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState<string>("");
  const [formPriority, setFormPriority] = useState<string>("medium");
  const [formStatus, setFormStatus] = useState<string>("backlog");
  const [formAssignee, setFormAssignee] = useState<string>("_none_");

  const createIssue = useCreateIssue();
  const { data: agentsResp } = useAgents({ page_size: 200 });
  const agents = agentsResp?.data ?? [];

  function handleCreate() {
    if (!formTitle.trim()) {
      toast.error("Title is required");
      return;
    }
    const body: Record<string, unknown> = {
      title: formTitle.trim(),
      status: formStatus,
      priority: formPriority,
    };
    if (formDescription.trim()) body.description = formDescription.trim();
    if (formCategory) body.category = formCategory;
    if (formAssignee && formAssignee !== "_none_") body.assignee_agent_uuid = formAssignee;

    createIssue.mutate(body, {
      onSuccess: () => {
        toast.success("Issue created");
        onOpenChange(false);
        setFormTitle("");
        setFormDescription("");
        setFormCategory("");
        setFormPriority("medium");
        setFormStatus("backlog");
        setFormAssignee("_none_");
      },
      onError: () => toast.error("Failed to create issue"),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
              onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
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
              <Label>Status</Label>
              <Select value={formStatus} onValueChange={setFormStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>{formatStatus(s)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Priority</Label>
              <Select value={formPriority} onValueChange={setFormPriority}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select value={formCategory || undefined} onValueChange={setFormCategory}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((cat) => (
                    <SelectItem key={cat.uuid} value={cat.key}>{cat.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Assignee Agent</Label>
              <Select value={formAssignee} onValueChange={setFormAssignee}>
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none_">None</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.uuid} value={a.uuid}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={createIssue.isPending}>
            {createIssue.isPending ? "Creating..." : "Create Issue"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Issue Categories Dialog ─────────────────────────────────────────────────

function IssueCategoriesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<IssueCategoryDef | null>(null);
  const [pendingRows, setPendingRows] = useState<Array<{ id: string; label: string }>>([]);

  const { data: categoriesResp } = useIssueCategories();
  const categories = categoriesResp?.data ?? [];
  const createCategory = useCreateIssueCategory();
  const deleteCategory = useDeleteIssueCategory();
  const patchCategory = usePatchIssueCategory();

  function toKey(label: string): string {
    return label.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "").replace(/^[^a-z]+/, "");
  }

  function addPendingRow() {
    setPendingRows((prev) => [...prev, { id: crypto.randomUUID(), label: "" }]);
  }

  function removePendingRow(id: string) {
    setPendingRows((prev) => prev.filter((r) => r.id !== id));
  }

  function updatePendingRow(id: string, label: string) {
    setPendingRows((prev) => prev.map((r) => r.id === id ? { ...r, label } : r));
  }

  function savePendingRow(id: string) {
    const row = pendingRows.find((r) => r.id === id);
    if (!row) return;
    const label = row.label.trim();
    if (!label) { removePendingRow(id); return; }
    const key = toKey(label);
    if (!key) { toast.error("Label must start with a letter"); return; }
    createCategory.mutate(
      { key, label },
      {
        onSuccess: () => { toast.success("Category added"); removePendingRow(id); },
        onError: () => toast.error("Failed to add category"),
      },
    );
  }

  function startEdit(cat: IssueCategoryDef) {
    setEditingUuid(cat.uuid);
    setEditingLabel(cat.label);
  }

  function commitEdit() {
    if (!editingUuid || !editingLabel.trim()) return;
    patchCategory.mutate(
      { uuid: editingUuid, label: editingLabel.trim() },
      {
        onSuccess: () => { toast.success("Category updated"); setEditingUuid(null); },
        onError: () => toast.error("Failed to update category"),
      },
    );
  }

  function cancelEdit() { setEditingUuid(null); }

  function confirmDelete(cat: IssueCategoryDef) { setDeleteTarget(cat); }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteCategory.mutate(deleteTarget.uuid, {
      onSuccess: () => { toast.success(`"${deleteTarget.label}" deleted`); setDeleteTarget(null); },
      onError: () => toast.error("Failed to delete category"),
    });
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Issue Settings</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <p className="text-xs font-semibold text-foreground uppercase tracking-wider">Categories</p>
            <div className="space-y-0.5">
              {categories.map((cat) => (
                <div key={cat.uuid} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-muted/30">
                  {editingUuid === cat.uuid ? (
                    <>
                      <Input
                        value={editingLabel}
                        onChange={(e) => setEditingLabel(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }}
                        autoFocus
                        className="h-7 text-xs flex-1"
                      />
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-teal" onClick={commitEdit} disabled={patchCategory.isPending}>
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-dim" onClick={cancelEdit}>
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <span className="text-sm text-foreground truncate">{cat.label}</span>
                        <span className="text-[10px] font-mono text-dim">{cat.key}</span>
                        {cat.is_system && (
                          <Badge variant="outline" className="text-[9px] text-dim border-dim/30 h-4 px-1">System</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-0.5">
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-dim hover:text-teal" onClick={() => startEdit(cat)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className={cn(
                            "h-6 w-6 p-0",
                            cat.is_system
                              ? "text-dim/30 cursor-not-allowed"
                              : "text-red-threat hover:text-red-threat/80",
                          )}
                          onClick={() => { if (!cat.is_system) confirmDelete(cat); }}
                          disabled={cat.is_system}
                          title={cat.is_system ? "System categories cannot be deleted" : "Delete"}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ))}
              {/* Pending new rows */}
              {pendingRows.map((row) => (
                <div key={row.id} className="flex items-center gap-1.5 px-2 py-1">
                  <Input
                    value={row.label}
                    onChange={(e) => updatePendingRow(row.id, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") savePendingRow(row.id);
                      if (e.key === "Escape") removePendingRow(row.id);
                    }}
                    placeholder="Category label..."
                    autoFocus
                    className="h-7 text-xs flex-1"
                  />
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-teal shrink-0" onClick={() => savePendingRow(row.id)} disabled={createCategory.isPending}>
                    <Check className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-dim hover:text-red-threat shrink-0" onClick={() => removePendingRow(row.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={addPendingRow}
              className="text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40 h-7 w-full mt-1"
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Category
            </Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null); }}
        title="Delete Category"
        description={`Delete "${deleteTarget?.label}"? Issues using this category will keep the key but it won't appear in the list.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function IssuesPage() {
  const [view, setView] = useState<"list" | "board">("board");
  const [showNewIssue, setShowNewIssue] = useState(false);
  const [showCategoriesSettings, setShowCategoriesSettings] = useState(false);

  // Categories from API
  const { data: categoriesResp } = useIssueCategories();
  const categories = categoriesResp?.data ?? [];
  const categoryMap: Record<string, string> = Object.fromEntries(
    categories.map((c) => [c.key, c.label]),
  );

  // Filters
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");

  // Debounce search
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  // Kanban drag state
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [localStatusMap, setLocalStatusMap] = useState<Record<string, string>>({});

  const queryParams: Record<string, string | number | boolean | undefined> = { page_size: 500 };
  if (debouncedSearch) queryParams.q = debouncedSearch;
  if (statusFilter) queryParams.status = statusFilter;
  if (priorityFilter) queryParams.priority = priorityFilter;

  const { data, isLoading, refetch, isFetching } = useIssues(queryParams);
  const patchIssue = usePatchIssue();

  const rawIssues = data?.data ?? [];
  const issues: AgentIssue[] = rawIssues.map((issue) =>
    localStatusMap[issue.uuid] !== undefined
      ? { ...issue, status: localStatusMap[issue.uuid] }
      : issue,
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const activeIssue = activeId ? issues.find((i) => i.uuid === activeId) ?? null : null;

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
      const overIdStr = String(over.id);

      let targetCol = KANBAN_COLUMNS.find((c) => c.key === overIdStr) ?? null;
      if (!targetCol) {
        const overIssue = issues.find((i) => i.uuid === overIdStr);
        if (overIssue) {
          const colKey = getColumnForStatus(overIssue.status);
          targetCol = KANBAN_COLUMNS.find((c) => c.key === colKey) ?? null;
        }
      }
      if (!targetCol) return;

      const draggedIssue = issues.find((i) => i.uuid === draggedUuid);
      if (!draggedIssue) return;

      const currentColKey = getColumnForStatus(draggedIssue.status);
      if (currentColKey === targetCol.key) return;

      const newStatus = targetCol.dropStatus;
      const prevStatus = draggedIssue.status;

      setLocalStatusMap((prev) => ({ ...prev, [draggedUuid]: newStatus }));

      patchIssue.mutate(
        { uuid: draggedUuid, body: { status: newStatus } },
        {
          onSuccess: () => {
            setLocalStatusMap((prev) => {
              const next = { ...prev };
              delete next[draggedUuid];
              return next;
            });
          },
          onError: () => {
            setLocalStatusMap((prev) => ({ ...prev, [draggedUuid]: prevStatus }));
            toast.error("Failed to move issue");
          },
        },
      );
    },
    [issues, patchIssue],
  );

  return (
    <AppLayout title="Issues">
      <div className="h-full flex flex-col gap-4">
        {/* Top bar */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Search */}
          <div className="relative flex-1 max-w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-dim" />
            <Input
              placeholder="Search issues..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-dim hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Status filter */}
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>{formatStatus(s)}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Priority filter */}
          <Select value={priorityFilter || "all"} onValueChange={(v) => setPriorityFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Priorities</SelectItem>
              {PRIORITIES.map((p) => (
                <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex-1" />

          {/* View toggle */}
          <div className="flex items-center border border-border rounded-md overflow-hidden">
            <button
              onClick={() => setView("list")}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 text-xs transition-colors",
                view === "list" ? "bg-teal/15 text-teal-light" : "text-dim hover:bg-muted",
              )}
            >
              <LayoutList className="h-3.5 w-3.5" />
              List
            </button>
            <button
              onClick={() => setView("board")}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 text-xs transition-colors",
                view === "board" ? "bg-teal/15 text-teal-light" : "text-dim hover:bg-muted",
              )}
            >
              <Columns className="h-3.5 w-3.5" />
              Board
            </button>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowCategoriesSettings(true)}
            className="h-8 w-8 p-0 text-dim hover:text-teal"
            title="Issue Settings"
          >
            <Settings2 className="h-3.5 w-3.5" />
          </Button>

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

        {/* Content */}
        {isLoading ? (
          <div className="flex gap-4 overflow-x-auto pb-2 flex-1 min-h-0">
            {Array.from({ length: 4 }).map((_, ci) => (
              <div key={ci} className="shrink-0 w-[280px] h-full surface-1 rounded-lg border border-border p-3 space-y-3">
                <Skeleton className="h-5 w-24" />
                {Array.from({ length: 3 }).map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-4 space-y-2">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-3 w-24" />
                    </CardContent>
                  </Card>
                ))}
              </div>
            ))}
          </div>
        ) : view === "board" ? (
          <div className="flex-1 min-h-0 overflow-hidden">
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
            >
              <div className="flex gap-4 overflow-x-auto h-full pb-2">
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
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto">
            <ListView issues={issues} categoryMap={categoryMap} />
          </div>
        )}
      </div>

      <NewIssueDialog open={showNewIssue} onOpenChange={setShowNewIssue} categories={categories} />
      <IssueCategoriesDialog open={showCategoriesSettings} onOpenChange={setShowCategoriesSettings} />
    </AppLayout>
  );
}
