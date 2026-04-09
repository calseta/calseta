import { useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useIssue,
  useIssueComments,
  usePatchIssue,
  useAddIssueComment,
  useDeleteIssue,
  useAgents,
} from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ArrowLeft, Bot, User, Trash2, ExternalLink, Check, X } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";

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

const ISSUE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"];
const PRIORITIES = ["critical", "high", "medium", "low"];

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

// Inline-editable text field
function InlineEditField({
  value,
  onSave,
  multiline = false,
  placeholder = "Click to edit",
  className,
}: {
  value: string | null | undefined;
  onSave: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");

  function startEdit() {
    setDraft(value ?? "");
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    if (draft !== (value ?? "")) onSave(draft);
  }

  function cancel() {
    setEditing(false);
    setDraft(value ?? "");
  }

  if (editing) {
    return (
      <div className="space-y-1.5">
        {multiline ? (
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
            rows={4}
            className="text-sm resize-none"
          />
        ) : (
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
            className="text-sm font-semibold h-9"
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); commit(); }
              if (e.key === "Escape") cancel();
            }}
          />
        )}
        <div className="flex items-center gap-1.5">
          <Button size="sm" className="h-6 px-2 text-xs gap-1" onClick={commit}>
            <Check className="h-3 w-3" /> Save
          </Button>
          <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1" onClick={cancel}>
            <X className="h-3 w-3" /> Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={startEdit}
      className={cn(
        "cursor-pointer rounded-md px-1 -mx-1 hover:bg-muted/40 transition-colors",
        !value && "text-dim italic",
        className,
      )}
    >
      {value || placeholder}
    </div>
  );
}

// Property row in sidebar
function PropRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-dim shrink-0">{label}</span>
      <div className="text-xs text-foreground text-right">{children}</div>
    </div>
  );
}

export function IssueDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const navigate = useNavigate();
  const { data: issueResp, isLoading } = useIssue(uuid);
  const { data: commentsResp } = useIssueComments(uuid);
  const patchIssue = usePatchIssue();
  const addComment = useAddIssueComment();
  const deleteIssue = useDeleteIssue();
  const { data: agentsResp } = useAgents({ page_size: 200 });

  const [commentBody, setCommentBody] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const issue = issueResp?.data;
  const comments = commentsResp?.data ?? [];
  const agents = agentsResp?.data ?? [];

  function patch(body: Record<string, unknown>) {
    patchIssue.mutate({ uuid, body }, {
      onError: () => toast.error("Failed to update issue"),
    });
  }

  function handleAddComment() {
    const trimmed = commentBody.trim();
    if (!trimmed) return;
    addComment.mutate(
      { uuid, body: { body: trimmed } },
      {
        onSuccess: () => { toast.success("Comment added"); setCommentBody(""); },
        onError: () => toast.error("Failed to add comment"),
      },
    );
  }

  function handleDelete() {
    deleteIssue.mutate(uuid, {
      onSuccess: () => {
        toast.success("Issue deleted");
        navigate({ to: "/issues" });
      },
      onError: () => toast.error("Failed to delete issue"),
    });
  }

  if (isLoading) {
    return (
      <AppLayout title="Issue">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!issue) {
    return (
      <AppLayout title="Issue">
        <div className="text-center text-sm text-dim py-20">Issue not found</div>
      </AppLayout>
    );
  }

  const showDone = issue.status === "done" || issue.status === "cancelled";

  return (
    <AppLayout title={issue.title}>
      <div className="space-y-4">
        {/* Header bar */}
        <div className="flex items-center gap-3">
          <Link
            to="/issues"
            className="flex items-center gap-1.5 text-xs text-dim hover:text-teal transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Issues
          </Link>
          <span className="text-dim text-xs">/</span>
          <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">
            {issue.identifier}
          </Badge>
          <Badge variant="outline" className={cn("text-[10px]", statusColor(issue.status))}>
            {issue.status.replace(/_/g, " ")}
          </Badge>
          <Badge variant="outline" className={cn("text-[10px]", priorityColor(issue.priority))}>
            {issue.priority}
          </Badge>
        </div>

        {/* Two-column layout */}
        <div className="flex gap-6 items-start">
          {/* Left: Main content */}
          <div className="flex-1 min-w-0 space-y-4">
            {/* Title */}
            <div>
              <InlineEditField
                value={issue.title}
                onSave={(v) => patch({ title: v })}
                className="text-xl font-semibold text-foreground leading-snug"
                placeholder="Issue title"
              />
            </div>

            {/* Description */}
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1.5">Description</p>
              <InlineEditField
                value={issue.description}
                onSave={(v) => patch({ description: v })}
                multiline
                className="text-sm text-foreground whitespace-pre-wrap leading-relaxed"
                placeholder="Add a description..."
              />
            </div>

            {/* Resolution (only for done/cancelled) */}
            {showDone && (
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1.5">Resolution</p>
                <InlineEditField
                  value={issue.resolution}
                  onSave={(v) => patch({ resolution: v })}
                  multiline
                  className="text-sm text-foreground whitespace-pre-wrap leading-relaxed"
                  placeholder="Document the resolution..."
                />
              </div>
            )}

            <Separator />

            {/* Comments */}
            <div className="space-y-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-dim">
                Comments {comments.length > 0 && `(${comments.length})`}
              </p>

              {comments.length === 0 ? (
                <p className="text-xs text-dim py-4">No comments yet.</p>
              ) : (
                <div className="space-y-3">
                  {comments.map((comment) => (
                    <div key={comment.uuid} className="flex gap-3">
                      <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                        {comment.author_agent_uuid ? (
                          <Bot className="h-3.5 w-3.5 text-teal" />
                        ) : (
                          <User className="h-3.5 w-3.5 text-dim" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-foreground">
                            {comment.author_operator ?? "Operator"}
                          </span>
                          {comment.author_agent_uuid && (
                            <Badge variant="outline" className="text-[10px] text-teal border-teal/30 bg-teal/10 px-1 py-0">
                              Agent
                            </Badge>
                          )}
                          <span className="text-[11px] text-dim">{relativeTime(comment.created_at)}</span>
                        </div>
                        <Card className="bg-muted/20">
                          <CardContent className="p-3">
                            <p className="text-sm text-foreground whitespace-pre-wrap">{comment.body}</p>
                          </CardContent>
                        </Card>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Add comment */}
              <div className="flex gap-3">
                <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                  <User className="h-3.5 w-3.5 text-dim" />
                </div>
                <div className="flex-1 space-y-2">
                  <Textarea
                    placeholder="Add a comment..."
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    rows={3}
                    className="text-sm resize-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleAddComment();
                    }}
                  />
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-dim">Cmd+Enter to submit</span>
                    <Button
                      size="sm"
                      onClick={handleAddComment}
                      disabled={!commentBody.trim() || addComment.isPending}
                      className="h-7 text-xs"
                    >
                      {addComment.isPending ? "Posting..." : "Comment"}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Properties sidebar */}
          <div className="w-64 shrink-0 space-y-4">
            <Card className="bg-card border-border">
              <CardContent className="p-4 space-y-0.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-dim mb-2">Properties</p>

                <PropRow label="Status">
                  <Select value={issue.status} onValueChange={(v) => patch({ status: v })}>
                    <SelectTrigger className="h-6 text-xs border-0 bg-transparent p-0 shadow-none w-auto gap-1 hover:bg-muted rounded">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ISSUE_STATUSES.map((s) => (
                        <SelectItem key={s} value={s} className="text-xs">{s.replace(/_/g, " ")}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </PropRow>

                <PropRow label="Priority">
                  <Select value={issue.priority} onValueChange={(v) => patch({ priority: v })}>
                    <SelectTrigger className="h-6 text-xs border-0 bg-transparent p-0 shadow-none w-auto gap-1 hover:bg-muted rounded">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITIES.map((p) => (
                        <SelectItem key={p} value={p} className="text-xs">{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </PropRow>

                <PropRow label="Category">
                  <Select value={issue.category ?? ""} onValueChange={(v) => patch({ category: v })}>
                    <SelectTrigger className="h-6 text-xs border-0 bg-transparent p-0 shadow-none w-auto gap-1 hover:bg-muted rounded">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((cat) => (
                        <SelectItem key={cat} value={cat} className="text-xs">{CATEGORY_LABELS[cat]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </PropRow>

                <PropRow label="Assignee">
                  <Select
                    value={issue.assignee_agent_uuid ?? "_none_"}
                    onValueChange={(v) => patch({ assignee_agent_uuid: v === "_none_" ? null : v })}
                  >
                    <SelectTrigger className="h-6 text-xs border-0 bg-transparent p-0 shadow-none w-auto gap-1 hover:bg-muted rounded">
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none_" className="text-xs">None</SelectItem>
                      {agents.map((a) => (
                        <SelectItem key={a.uuid} value={a.uuid} className="text-xs">{a.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </PropRow>
              </CardContent>
            </Card>

            {/* Timestamps */}
            <Card className="bg-card border-border">
              <CardContent className="p-4 space-y-0.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-dim mb-2">Timeline</p>
                <PropRow label="Created"><span className="text-dim">{formatDate(issue.created_at)}</span></PropRow>
                <PropRow label="Updated"><span className="text-dim">{formatDate(issue.updated_at)}</span></PropRow>
                {issue.started_at && (
                  <PropRow label="Started"><span className="text-dim">{formatDate(issue.started_at)}</span></PropRow>
                )}
                {issue.completed_at && (
                  <PropRow label="Completed"><span className="text-teal">{formatDate(issue.completed_at)}</span></PropRow>
                )}
                {issue.cancelled_at && (
                  <PropRow label="Cancelled"><span className="text-red-threat">{formatDate(issue.cancelled_at)}</span></PropRow>
                )}
                {issue.due_at && (
                  <PropRow label="Due"><span className="text-amber">{formatDate(issue.due_at)}</span></PropRow>
                )}
              </CardContent>
            </Card>

            {/* Linked Entities */}
            {(issue.alert_uuid || issue.routine_uuid || issue.parent_uuid) && (
              <Card className="bg-card border-border">
                <CardContent className="p-4 space-y-0.5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-dim mb-2">Linked To</p>
                  {issue.alert_uuid && (
                    <PropRow label="Alert">
                      <Link
                        to="/alerts/$uuid"
                        params={{ uuid: issue.alert_uuid }}
                        search={{ tab: "indicators" }}
                        className="text-teal hover:text-teal-light flex items-center gap-1"
                      >
                        <span className="font-mono">{issue.alert_uuid.slice(0, 8)}...</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </PropRow>
                  )}
                  {issue.routine_uuid && (
                    <PropRow label="Routine">
                      <Link
                        to="/routines/$uuid"
                        params={{ uuid: issue.routine_uuid }}
                        search={{ tab: "configuration" }}
                        className="text-teal hover:text-teal-light flex items-center gap-1"
                      >
                        <span className="font-mono">{issue.routine_uuid.slice(0, 8)}...</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </PropRow>
                  )}
                  {issue.parent_uuid && (
                    <PropRow label="Parent">
                      <Link
                        to="/issues/$uuid"
                        params={{ uuid: issue.parent_uuid }}
                        search={{ tab: "details" }}
                        className="text-teal hover:text-teal-light flex items-center gap-1"
                      >
                        <span className="font-mono">{issue.parent_uuid.slice(0, 8)}...</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </PropRow>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Danger zone */}
            <Button
              variant="ghost"
              size="sm"
              className="w-full h-8 text-xs text-red-threat hover:bg-red-threat/10 hover:text-red-threat gap-1.5"
              onClick={() => setShowDeleteConfirm(true)}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete Issue
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Issue"
        description={`This will permanently delete ${issue.identifier}. This action cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
