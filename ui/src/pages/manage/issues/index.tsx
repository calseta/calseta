import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { useIssues, useCreateIssue } from "@/hooks/use-api";
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

function IssueCard({ issue }: { issue: AgentIssue }) {
  const navigate = useNavigate();

  return (
    <Card
      className="cursor-pointer hover:border-teal/40 transition-colors"
      onClick={() => navigate({ to: "/manage/issues/$uuid", params: { uuid: issue.uuid }, search: { tab: "details" } })}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">
              {issue.identifier}
            </Badge>
            <Badge
              variant="outline"
              className={cn("text-[10px]", priorityColor(issue.priority))}
            >
              {issue.priority}
            </Badge>
            <Badge variant="outline" className="text-[10px] text-dim border-dim/30">
              {CATEGORY_LABELS[issue.category] ?? issue.category}
            </Badge>
          </div>
          <Badge
            variant="outline"
            className={cn("text-[10px] shrink-0", issueStatusColor(issue.status))}
          >
            {issue.status}
          </Badge>
        </div>
        <p className="text-sm text-foreground font-medium leading-snug">{issue.title}</p>
        <div className="flex items-center justify-between text-[11px] text-dim">
          <span>{issue.assignee_operator ?? issue.assignee_agent_uuid ?? "Unassigned"}</span>
          <span>{relativeTime(issue.created_at)}</span>
        </div>
      </CardContent>
    </Card>
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
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [priorityFilter, setPriorityFilter] = useState<string | null>(null);
  const [showNewIssue, setShowNewIssue] = useState(false);

  // Form state
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState<string>("");
  const [formPriority, setFormPriority] = useState<string>("");

  const params: Record<string, string | number | boolean | undefined> = {
    page_size: 200,
  };
  if (categoryFilter) params.category = categoryFilter;
  if (priorityFilter) params.priority = priorityFilter;

  const { data, isLoading, refetch, isFetching } = useIssues(params);
  const createIssue = useCreateIssue();

  const issues = data?.data ?? [];

  function filterIssues(statuses: string[]): AgentIssue[] {
    return issues.filter((i) => statuses.includes(i.status));
  }

  const openIssues = filterIssues(["backlog", "todo"]);
  const inProgressIssues = filterIssues(["in_progress", "in_review"]);
  const doneIssues = filterIssues(["done"]);
  const blockedIssues = filterIssues(["blocked", "cancelled"]);

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
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>

            {/* Category chips */}
            <div className="flex items-center gap-1 flex-wrap">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                  className={cn(
                    "text-[11px] px-2 py-0.5 rounded border transition-colors",
                    categoryFilter === cat
                      ? "border-teal text-teal bg-teal/10"
                      : "border-border text-dim hover:border-teal/40 hover:text-foreground",
                  )}
                >
                  {CATEGORY_LABELS[cat]}
                </button>
              ))}
            </div>

            {/* Priority filter */}
            <Select
              value={priorityFilter ?? "all"}
              onValueChange={(v) => setPriorityFilter(v === "all" ? null : v)}
            >
              <SelectTrigger className="h-7 text-xs w-32">
                <SelectValue placeholder="Priority" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All priorities</SelectItem>
                {PRIORITIES.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button size="sm" onClick={() => setShowNewIssue(true)} className="h-8 gap-1">
            <Plus className="h-3.5 w-3.5" />
            New Issue
          </Button>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="open">
          <TabsList>
            <TabsTrigger value="open">
              Open
              {!isLoading && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {openIssues.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="in_progress">
              In Progress
              {!isLoading && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {inProgressIssues.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="done">
              Done
              {!isLoading && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {doneIssues.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="blocked">
              Blocked / Cancelled
              {!isLoading && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {blockedIssues.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          {isLoading ? (
            <div className="mt-4 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <IssueCardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <>
              <TabsContent value="open" className="mt-4 space-y-3">
                {openIssues.length === 0 ? (
                  <div className="text-center text-sm text-dim py-20">No open issues</div>
                ) : (
                  openIssues.map((issue) => <IssueCard key={issue.uuid} issue={issue} />)
                )}
              </TabsContent>

              <TabsContent value="in_progress" className="mt-4 space-y-3">
                {inProgressIssues.length === 0 ? (
                  <div className="text-center text-sm text-dim py-20">No in-progress issues</div>
                ) : (
                  inProgressIssues.map((issue) => <IssueCard key={issue.uuid} issue={issue} />)
                )}
              </TabsContent>

              <TabsContent value="done" className="mt-4 space-y-3">
                {doneIssues.length === 0 ? (
                  <div className="text-center text-sm text-dim py-20">No completed issues</div>
                ) : (
                  doneIssues.map((issue) => <IssueCard key={issue.uuid} issue={issue} />)
                )}
              </TabsContent>

              <TabsContent value="blocked" className="mt-4 space-y-3">
                {blockedIssues.length === 0 ? (
                  <div className="text-center text-sm text-dim py-20">
                    No blocked or cancelled issues
                  </div>
                ) : (
                  blockedIssues.map((issue) => <IssueCard key={issue.uuid} issue={issue} />)
                )}
              </TabsContent>
            </>
          )}
        </Tabs>
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
