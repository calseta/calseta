import { useState } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DetailPageHeader,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
} from "@/components/detail-page";
import { MarkdownPreview } from "@/components/markdown-preview";
import {
  useKBPage,
  useKBRevisions,
  useSyncKBPage,
  useAddKBPageLink,
} from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Edit2, RefreshCw, Link as LinkIcon, Plus } from "lucide-react";
import type { KBPageRevision, KBPageLink } from "@/lib/types";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function statusColor(status: string): string {
  switch (status) {
    case "published":
      return "text-teal bg-teal/10 border-teal/30";
    case "draft":
      return "text-amber bg-amber/10 border-amber/30";
    case "archived":
      return "text-muted-foreground bg-muted/10 border-muted/30";
    default:
      return "text-muted-foreground bg-muted/10 border-muted/30";
  }
}

function syncOutcomeColor(outcome: string): string {
  switch (outcome) {
    case "updated":
      return "text-teal bg-teal/10 border-teal/30";
    case "no_change":
      return "text-muted-foreground bg-muted/10 border-muted/30";
    case "fetch_failed":
    case "config_invalid":
      return "text-red-500 bg-red-500/10 border-red-500/30";
    default:
      return "text-muted-foreground bg-muted/10 border-muted/30";
  }
}

function entityTypeBadgeColor(type: string): string {
  switch (type) {
    case "alert":
      return "text-red-500 bg-red-500/10 border-red-500/30";
    case "issue":
      return "text-amber bg-amber/10 border-amber/30";
    case "page":
      return "text-teal bg-teal/10 border-teal/30";
    case "agent":
      return "text-muted-foreground bg-muted/10 border-muted/30";
    default:
      return "text-muted-foreground bg-muted/10 border-muted/30";
  }
}

/* -------------------------------------------------------------------------- */
/*  RevisionRow                                                                */
/* -------------------------------------------------------------------------- */

function RevisionRow({
  revision,
  expanded,
  onToggle,
}: {
  revision: KBPageRevision;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="border-b border-border hover:bg-accent/30 transition-colors">
        <td className="px-3 py-2.5 text-xs font-mono text-muted-foreground">
          v{revision.revision_number}
        </td>
        <td className="px-3 py-2.5 text-sm text-foreground">
          {revision.change_summary ?? (
            <span className="text-muted-foreground italic">no summary</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {revision.author_operator ?? "—"}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {formatDate(revision.created_at)}
        </td>
        <td className="px-3 py-2.5">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onToggle}>
            {expanded ? "Hide" : "View"}
          </Button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-card/50">
          <td colSpan={5} className="px-3 py-3">
            <pre className="text-xs font-mono whitespace-pre-wrap break-words text-muted-foreground rounded-md bg-muted/30 p-3 max-h-64 overflow-y-auto">
              {revision.body}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/*  Add Link Dialog                                                            */
/* -------------------------------------------------------------------------- */

interface AddLinkDialogProps {
  open: boolean;
  onClose: () => void;
  slug: string;
}

const ENTITY_TYPES = ["alert", "issue", "page", "agent"] as const;
const LINK_TYPES = ["reference", "source", "generated_from", "related"] as const;

function AddLinkDialog({ open, onClose, slug }: AddLinkDialogProps) {
  const addLink = useAddKBPageLink();
  const [entityType, setEntityType] = useState<string>("alert");
  const [entityId, setEntityId] = useState("");
  const [linkType, setLinkType] = useState<string>("reference");

  async function handleSubmit() {
    if (!entityId.trim()) {
      toast.error("Entity ID is required");
      return;
    }
    try {
      await addLink.mutateAsync({
        slug,
        body: {
          linked_entity_type: entityType,
          linked_entity_id: entityId.trim(),
          link_type: linkType,
        },
      });
      toast.success("Link added");
      setEntityId("");
      onClose();
    } catch {
      toast.error("Failed to add link");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Link</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Entity Type</Label>
            <Select value={entityType} onValueChange={setEntityType}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENTITY_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="link-entity-id">Entity ID (UUID)</Label>
            <Input
              id="link-entity-id"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Link Type</Label>
            <Select value={linkType} onValueChange={setLinkType}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LINK_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={addLink.isPending}>
            {addLink.isPending ? "Adding..." : "Add Link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* -------------------------------------------------------------------------- */
/*  KBDetailPage                                                               */
/* -------------------------------------------------------------------------- */

export function KBDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { slug, tab } = useSearch({ strict: false }) as {
    slug: string;
    tab?: string;
  };
  const navigate = useNavigate();

  const page = useKBPage(slug ?? "");
  const revisions = useKBRevisions(slug ?? "");
  const syncPage = useSyncKBPage();

  const [activeTab, setActiveTab] = useState(tab ?? "content");
  const [expandedRevision, setExpandedRevision] = useState<string | null>(null);
  const [showAddLink, setShowAddLink] = useState(false);
  const [syncOutcome, setSyncOutcome] = useState<string | null>(null);

  const data = page.data?.data;
  const isSynced = !!data?.sync_source;

  async function handleSync() {
    if (!slug) return;
    setSyncOutcome(null);
    try {
      const result = await syncPage.mutateAsync(slug);
      setSyncOutcome(result.data.outcome);
      toast.success(`Sync complete: ${result.data.outcome}`);
    } catch {
      toast.error("Sync failed");
    }
  }

  function handleEditClick() {
    void navigate({
      to: "/manage/kb/$uuid/edit",
      params: { uuid },
      search: { slug },
    });
  }

  if (!slug) {
    return (
      <AppLayout title="Knowledge Base">
        <div className="p-6 text-sm text-muted-foreground">
          Invalid page reference — no slug provided.
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title={data?.title ?? "Knowledge Base"}>
      <div className="p-6 space-y-6 max-w-6xl">
        {/* Header */}
        {page.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-7 w-80" />
          </div>
        ) : data ? (
          <DetailPageHeader
            backTo="/manage/kb"
            title={data.title}
            badges={
              <Badge
                variant="outline"
                className={cn("text-xs capitalize", statusColor(data.status))}
              >
                {data.status}
              </Badge>
            }
            subtitle={
              <span className="text-xs font-mono text-muted-foreground">
                {data.slug}
              </span>
            }
            actions={
              <Button
                size="sm"
                variant="outline"
                onClick={handleEditClick}
                disabled={isSynced}
                title={
                  isSynced
                    ? "Managed by sync — edit at source"
                    : "Edit this page"
                }
                className="gap-1.5"
              >
                <Edit2 className="h-3.5 w-3.5" />
                Edit
              </Button>
            }
          />
        ) : (
          <div className="text-sm text-muted-foreground">Page not found.</div>
        )}

        {data && (
          <DetailPageLayout
            sidebar={
              <DetailPageSidebar>
                <SidebarSection title="Details">
                  <DetailPageField label="Folder" value={data.folder} mono />
                  <DetailPageField
                    label="Status"
                    value={
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs capitalize",
                          statusColor(data.status),
                        )}
                      >
                        {data.status}
                      </Badge>
                    }
                  />
                  <DetailPageField
                    label="Format"
                    value={data.format}
                    mono
                  />
                  <DetailPageField
                    label="Priority"
                    value={String(data.inject_priority)}
                  />
                  <DetailPageField
                    label="Pinned"
                    value={data.inject_pinned ? "Yes" : "No"}
                  />
                  <DetailPageField
                    label="Tokens"
                    value={
                      data.token_count != null
                        ? data.token_count.toLocaleString()
                        : "—"
                    }
                  />
                  <DetailPageField
                    label="Revision"
                    value={`v${data.latest_revision_number}`}
                    mono
                  />
                </SidebarSection>
                <SidebarSection title="Scope">
                  {!data.inject_scope ? (
                    <span className="text-xs text-muted-foreground">
                      No scope set
                    </span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {(data.inject_scope as { global?: boolean }).global && (
                        <Badge
                          variant="outline"
                          className="text-xs text-teal bg-teal/10 border-teal/30"
                        >
                          global
                        </Badge>
                      )}
                      {Array.isArray((data.inject_scope as { roles?: unknown[] }).roles) &&
                        (data.inject_scope as { roles: unknown[] }).roles.length > 0 && (
                          <Badge
                            variant="outline"
                            className="text-xs text-amber bg-amber/10 border-amber/30"
                          >
                            {(data.inject_scope as { roles: unknown[] }).roles.length} role
                            {(data.inject_scope as { roles: unknown[] }).roles.length !== 1 ? "s" : ""}
                          </Badge>
                        )}
                      {Array.isArray((data.inject_scope as { agent_uuids?: unknown[] }).agent_uuids) &&
                        (data.inject_scope as { agent_uuids: unknown[] }).agent_uuids.length > 0 && (
                          <Badge
                            variant="outline"
                            className="text-xs text-muted-foreground bg-muted/10 border-muted/30"
                          >
                            {(data.inject_scope as { agent_uuids: unknown[] }).agent_uuids.length} agent
                            {(data.inject_scope as { agent_uuids: unknown[] }).agent_uuids.length !== 1
                              ? "s"
                              : ""}
                          </Badge>
                        )}
                    </div>
                  )}
                </SidebarSection>
                <SidebarSection title="Timestamps">
                  <DetailPageField
                    label="Created"
                    value={relativeTime(data.created_at)}
                  />
                  <DetailPageField
                    label="Updated"
                    value={relativeTime(data.updated_at)}
                  />
                  {data.synced_at && (
                    <DetailPageField
                      label="Synced"
                      value={relativeTime(data.synced_at)}
                    />
                  )}
                </SidebarSection>
              </DetailPageSidebar>
            }
          >
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="content">Content</TabsTrigger>
                <TabsTrigger value="revisions">
                  Revisions
                  {revisions.data && (
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      ({revisions.data.meta.total})
                    </span>
                  )}
                </TabsTrigger>
                <TabsTrigger value="links">
                  Links
                  {data.links.length > 0 && (
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      ({data.links.length})
                    </span>
                  )}
                </TabsTrigger>
                {isSynced && (
                  <TabsTrigger value="sync">Sync</TabsTrigger>
                )}
              </TabsList>

              {/* Content tab */}
              <TabsContent value="content" className="mt-4">
                {data.body ? (
                  <div className="rounded-lg border border-border bg-card p-6">
                    <MarkdownPreview content={data.body} />
                  </div>
                ) : (
                  <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground italic">
                    This page has no content yet.
                  </div>
                )}
              </TabsContent>

              {/* Revisions tab */}
              <TabsContent value="revisions" className="mt-4">
                {revisions.isLoading ? (
                  <div className="space-y-2">
                    {[...Array(4)].map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : revisions.data?.data.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">
                    No revisions recorded yet.
                  </p>
                ) : (
                  <div className="rounded-lg border border-border overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-16">
                            Rev
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">
                            Summary
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-32">
                            Author
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-36">
                            Created
                          </th>
                          <th className="px-3 py-2 w-16" />
                        </tr>
                      </thead>
                      <tbody>
                        {revisions.data?.data.map((rev) => (
                          <RevisionRow
                            key={rev.uuid}
                            revision={rev}
                            expanded={expandedRevision === rev.uuid}
                            onToggle={() =>
                              setExpandedRevision((prev) =>
                                prev === rev.uuid ? null : rev.uuid,
                              )
                            }
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </TabsContent>

              {/* Links tab */}
              <TabsContent value="links" className="mt-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm text-muted-foreground">
                    Linked entities
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 h-7 text-xs"
                    onClick={() => setShowAddLink(true)}
                  >
                    <Plus className="h-3 w-3" />
                    Add link
                  </Button>
                </div>
                {data.links.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-6 text-center">
                    <LinkIcon className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      No links yet. Connect this page to alerts, issues, agents,
                      or other pages.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-lg border border-border overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-28">
                            Type
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">
                            Entity ID
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-32">
                            Link Type
                          </th>
                          <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-36">
                            Added
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.links.map((link) => (
                          <LinkRow key={link.uuid} link={link} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </TabsContent>

              {/* Sync tab */}
              {isSynced && (
                <TabsContent value="sync" className="mt-4">
                  <div className="space-y-4">
                    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-xs text-muted-foreground block mb-0.5">
                            Source Type
                          </span>
                          <span className="font-medium">
                            {typeof data.sync_source === "object" &&
                            data.sync_source !== null &&
                            "type" in data.sync_source
                              ? String(data.sync_source.type)
                              : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="text-xs text-muted-foreground block mb-0.5">
                            Last Synced
                          </span>
                          <span className="font-medium">
                            {data.synced_at
                              ? relativeTime(data.synced_at)
                              : "Never"}
                          </span>
                        </div>
                        <div className="col-span-2">
                          <span className="text-xs text-muted-foreground block mb-0.5">
                            Source URL
                          </span>
                          <span className="font-mono text-xs break-all">
                            {typeof data.sync_source === "object" &&
                            data.sync_source !== null &&
                            "url" in data.sync_source
                              ? String(data.sync_source.url)
                              : "—"}
                          </span>
                        </div>
                        {data.sync_last_hash && (
                          <div className="col-span-2">
                            <span className="text-xs text-muted-foreground block mb-0.5">
                              Last Hash
                            </span>
                            <span className="font-mono text-xs text-muted-foreground">
                              {data.sync_last_hash}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Button
                        size="sm"
                        onClick={handleSync}
                        disabled={syncPage.isPending}
                        className="gap-1.5"
                      >
                        <RefreshCw
                          className={cn(
                            "h-3.5 w-3.5",
                            syncPage.isPending && "animate-spin",
                          )}
                        />
                        {syncPage.isPending ? "Syncing..." : "Sync now"}
                      </Button>
                      {syncOutcome && (
                        <Badge
                          variant="outline"
                          className={cn("text-xs", syncOutcomeColor(syncOutcome))}
                        >
                          {syncOutcome}
                        </Badge>
                      )}
                    </div>
                  </div>
                </TabsContent>
              )}
            </Tabs>
          </DetailPageLayout>
        )}
      </div>

      {slug && (
        <AddLinkDialog
          open={showAddLink}
          onClose={() => setShowAddLink(false)}
          slug={slug}
        />
      )}
    </AppLayout>
  );
}

/* -------------------------------------------------------------------------- */
/*  LinkRow                                                                    */
/* -------------------------------------------------------------------------- */

function LinkRow({ link }: { link: KBPageLink }) {
  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30 transition-colors">
      <td className="px-3 py-2.5">
        <Badge
          variant="outline"
          className={cn("text-xs", entityTypeBadgeColor(link.linked_entity_type))}
        >
          {link.linked_entity_type}
        </Badge>
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground truncate max-w-[200px]">
        {link.linked_entity_id}
      </td>
      <td className="px-3 py-2.5 text-xs text-muted-foreground">
        {link.link_type}
      </td>
      <td className="px-3 py-2.5 text-xs text-muted-foreground">
        {relativeTime(link.created_at)}
      </td>
    </tr>
  );
}
