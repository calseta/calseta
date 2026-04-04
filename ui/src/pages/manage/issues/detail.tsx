import { useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  DetailPageHeader,
  DetailPageField,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
} from "@/components/detail-page";
import { MarkdownPreview } from "@/components/markdown-preview";
import {
  useIssue,
  useIssueComments,
  usePatchIssue,
  useAddIssueComment,
} from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ExternalLink } from "lucide-react";

const CATEGORY_LABELS: Record<string, string> = {
  remediation: "Remediation",
  detection_tuning: "Detection Tuning",
  investigation: "Investigation",
  compliance: "Compliance",
  post_incident: "Post Incident",
  maintenance: "Maintenance",
  custom: "Custom",
};

const ISSUE_STATUSES = [
  "backlog",
  "todo",
  "in_progress",
  "in_review",
  "done",
  "blocked",
  "cancelled",
];

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

export function IssueDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data: issueResp, isLoading, refetch, isFetching } = useIssue(uuid);
  const { data: commentsResp, refetch: refetchComments } = useIssueComments(uuid);
  const patchIssue = usePatchIssue();
  const addComment = useAddIssueComment();

  const [commentBody, setCommentBody] = useState("");

  const issue = issueResp?.data;
  const comments = commentsResp?.data ?? [];

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

  function handleStatusChange(newStatus: string) {
    patchIssue.mutate(
      { uuid, body: { status: newStatus } },
      {
        onSuccess: () => toast.success(`Issue moved to ${newStatus}`),
        onError: () => toast.error("Failed to update status"),
      },
    );
  }

  function handleAddComment() {
    const trimmed = commentBody.trim();
    if (!trimmed) return;
    addComment.mutate(
      { uuid, body: { body: trimmed } },
      {
        onSuccess: () => {
          toast.success("Comment added");
          setCommentBody("");
          refetchComments();
        },
        onError: () => toast.error("Failed to add comment"),
      },
    );
  }

  return (
    <AppLayout title={issue.title}>
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/issues"
          title={issue.title}
          badges={
            <>
              <Badge variant="outline" className="text-[10px] font-mono text-dim border-dim/30">
                {issue.identifier}
              </Badge>
              <Badge
                variant="outline"
                className={cn("text-[10px]", issueStatusColor(issue.status))}
              >
                {issue.status}
              </Badge>
              <Badge
                variant="outline"
                className={cn("text-[10px]", priorityColor(issue.priority))}
              >
                {issue.priority}
              </Badge>
            </>
          }
          actions={
            <Select value={issue.status} onValueChange={handleStatusChange}>
              <SelectTrigger className="h-8 text-xs w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ISSUE_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
          onRefresh={() => { refetch(); refetchComments(); }}
          isRefreshing={isFetching}
        />

        <Tabs defaultValue="details">
          <TabsList>
            <TabsTrigger value="details">Details</TabsTrigger>
            <TabsTrigger value="comments">
              Comments
              {comments.length > 0 && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {comments.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          {/* Details tab */}
          <TabsContent value="details" className="mt-4">
            <DetailPageLayout
              sidebar={
                <DetailPageSidebar>
                  <SidebarSection title="Properties">
                    <DetailPageField label="Category" value={CATEGORY_LABELS[issue.category] ?? issue.category} />
                    <DetailPageField label="Priority" value={issue.priority} />
                    <DetailPageField label="Status" value={issue.status} />
                    <DetailPageField
                      label="Assignee"
                      value={issue.assignee_operator ?? issue.assignee_agent_uuid ?? "—"}
                    />
                    <DetailPageField
                      label="Created by"
                      value={issue.created_by_operator ?? issue.created_by_agent_uuid ?? "—"}
                    />
                    <DetailPageField label="Created" value={formatDate(issue.created_at)} />
                    <DetailPageField label="Updated" value={formatDate(issue.updated_at)} />
                    {issue.due_at && (
                      <DetailPageField label="Due" value={formatDate(issue.due_at)} />
                    )}
                    {issue.started_at && (
                      <DetailPageField label="Started" value={formatDate(issue.started_at)} />
                    )}
                    {issue.completed_at && (
                      <DetailPageField label="Completed" value={formatDate(issue.completed_at)} />
                    )}
                    {issue.cancelled_at && (
                      <DetailPageField label="Cancelled" value={formatDate(issue.cancelled_at)} />
                    )}
                  </SidebarSection>

                  {(issue.alert_uuid || issue.routine_uuid || issue.parent_uuid) && (
                    <SidebarSection title="Linked Entities">
                      {issue.alert_uuid && (
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground">Alert</span>
                          <Link
                            to="/alerts/$uuid"
                            params={{ uuid: issue.alert_uuid }}
                            search={{ tab: "indicators" }}
                            className="text-xs text-teal hover:text-teal-light flex items-center gap-1"
                          >
                            <span className="font-mono truncate max-w-[120px]">
                              {issue.alert_uuid.slice(0, 8)}...
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </Link>
                        </div>
                      )}
                      {issue.routine_uuid && (
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground">Routine</span>
                          <Link
                            to="/manage/routines/$uuid"
                            params={{ uuid: issue.routine_uuid }}
                            search={{ tab: "configuration" }}
                            className="text-xs text-teal hover:text-teal-light flex items-center gap-1"
                          >
                            <span className="font-mono truncate max-w-[120px]">
                              {issue.routine_uuid.slice(0, 8)}...
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </Link>
                        </div>
                      )}
                      {issue.parent_uuid && (
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground">Parent</span>
                          <Link
                            to="/manage/issues/$uuid"
                            params={{ uuid: issue.parent_uuid }}
                            search={{ tab: "details" }}
                            className="text-xs text-teal hover:text-teal-light flex items-center gap-1"
                          >
                            <span className="font-mono truncate max-w-[120px]">
                              {issue.parent_uuid.slice(0, 8)}...
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </Link>
                        </div>
                      )}
                    </SidebarSection>
                  )}
                </DetailPageSidebar>
              }
            >
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Description</CardTitle>
                </CardHeader>
                <CardContent>
                  {issue.description ? (
                    <MarkdownPreview content={issue.description} />
                  ) : (
                    <p className="text-sm text-dim">No description provided.</p>
                  )}
                </CardContent>
              </Card>

              {issue.resolution && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium">Resolution</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-foreground">{issue.resolution}</p>
                  </CardContent>
                </Card>
              )}
            </DetailPageLayout>
          </TabsContent>

          {/* Comments tab */}
          <TabsContent value="comments" className="mt-4">
            <div className="space-y-4">
              {comments.length === 0 ? (
                <div className="text-center text-sm text-dim py-12">No comments yet</div>
              ) : (
                <div className="space-y-3">
                  {comments.map((comment) => (
                    <Card key={comment.uuid}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <span className="text-xs font-medium text-foreground">
                            {comment.author_operator ?? comment.author_agent_uuid ?? "Unknown"}
                          </span>
                          <span className="text-[11px] text-dim">
                            {relativeTime(comment.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-foreground whitespace-pre-wrap">{comment.body}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}

              <Separator />

              <Card>
                <CardContent className="p-4 space-y-3">
                  <Textarea
                    placeholder="Add a comment..."
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    rows={3}
                  />
                  <div className="flex justify-end">
                    <Button
                      size="sm"
                      onClick={handleAddComment}
                      disabled={!commentBody.trim() || addComment.isPending}
                    >
                      {addComment.isPending ? "Posting..." : "Add Comment"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
