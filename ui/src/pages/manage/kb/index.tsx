import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  ResizableTable,
  ResizableTableHead,
} from "@/components/ui/resizable-table";
import {
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useKBPages,
  useKBFolders,
  useKBSearch,
  useCreateKBPage,
} from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Folder, Search, Plus, RefreshCw } from "lucide-react";
import type { KBFolderNode, KBPageSummary, KBSearchResult } from "@/lib/types";

/* -------------------------------------------------------------------------- */
/*  InjectScopeBadges                                                          */
/* -------------------------------------------------------------------------- */

type InjectScope = { global?: boolean; roles?: unknown[]; agent_uuids?: unknown[] };

function InjectScopeBadges({
  scope,
}: {
  scope: Record<string, unknown> | null;
}) {
  if (!scope) return <span className="text-xs text-muted-foreground">—</span>;
  const s = scope as InjectScope;
  return (
    <div className="flex flex-wrap gap-1">
      {s.global && (
        <Badge
          variant="outline"
          className="text-xs text-teal bg-teal/10 border-teal/30"
        >
          global
        </Badge>
      )}
      {Array.isArray(s.roles) && s.roles.length > 0 && (
        <Badge
          variant="outline"
          className="text-xs text-amber bg-amber/10 border-amber/30"
        >
          role
        </Badge>
      )}
      {Array.isArray(s.agent_uuids) && s.agent_uuids.length > 0 && (
        <Badge
          variant="outline"
          className="text-xs text-muted-foreground bg-muted/10 border-muted/30"
        >
          agent
        </Badge>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  FolderTree                                                                 */
/* -------------------------------------------------------------------------- */

function FolderTree({
  nodes,
  selected,
  onSelect,
}: {
  nodes: KBFolderNode[];
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  return (
    <div className="space-y-0.5">
      {nodes.map((node) => (
        <div key={node.path}>
          <button
            onClick={() => onSelect(node.path)}
            className={cn(
              "flex w-full items-center justify-between px-2 py-1.5 rounded-md text-xs transition-colors",
              selected === node.path
                ? "bg-teal/15 text-teal"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            <span className="flex items-center gap-1.5">
              <Folder className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{node.name}</span>
            </span>
            <span className="text-muted-foreground shrink-0">
              {node.page_count}
            </span>
          </button>
          {node.children.length > 0 && (
            <div className="ml-4">
              <FolderTree
                nodes={node.children}
                selected={selected}
                onSelect={onSelect}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  SyncCell                                                                   */
/* -------------------------------------------------------------------------- */

function SyncCell({
  synced_at,
  sync_source,
}: {
  synced_at: string | null;
  sync_source: Record<string, unknown> | null;
}) {
  if (!sync_source)
    return <span className="text-xs text-muted-foreground">local</span>;
  if (synced_at)
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <RefreshCw className="h-3 w-3" />
        {relativeTime(synced_at)}
      </span>
    );
  return <span className="text-xs text-amber">pending</span>;
}

/* -------------------------------------------------------------------------- */
/*  New Page Dialog                                                            */
/* -------------------------------------------------------------------------- */

interface NewPageDialogProps {
  open: boolean;
  onClose: () => void;
}

function NewPageDialog({ open, onClose }: NewPageDialogProps) {
  const navigate = useNavigate();
  const createPage = useCreateKBPage();

  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [folder, setFolder] = useState("/");
  const [body, setBody] = useState("");
  const [globalScope, setGlobalScope] = useState(false);
  const [roles, setRoles] = useState("");
  const [agents, setAgents] = useState("");
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);

  function handleTitleChange(v: string) {
    setTitle(v);
    if (!slugManuallyEdited) {
      setSlug(v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
    }
  }

  function handleSlugChange(v: string) {
    setSlug(v);
    setSlugManuallyEdited(true);
  }

  function buildInjectScope(): Record<string, unknown> | null {
    const rolesArray = roles
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const agentsArray = agents
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!globalScope && rolesArray.length === 0 && agentsArray.length === 0)
      return null;
    return {
      ...(globalScope ? { global: true } : {}),
      ...(rolesArray.length > 0 ? { roles: rolesArray } : {}),
      ...(agentsArray.length > 0 ? { agent_uuids: agentsArray } : {}),
    };
  }

  async function handleSubmit() {
    if (!title.trim() || !slug.trim()) {
      toast.error("Title and slug are required");
      return;
    }
    try {
      const result = await createPage.mutateAsync({
        title: title.trim(),
        slug: slug.trim(),
        folder: folder.trim() || "/",
        body,
        inject_scope: buildInjectScope(),
      });
      toast.success("Page created");
      onClose();
      void navigate({
        to: "/manage/kb/$uuid",
        params: { uuid: result.data.uuid },
        search: { slug: result.data.slug, tab: "content" },
      });
    } catch {
      toast.error("Failed to create page");
    }
  }

  function handleClose() {
    setTitle("");
    setSlug("");
    setFolder("/");
    setBody("");
    setGlobalScope(false);
    setRoles("");
    setAgents("");
    setSlugManuallyEdited(false);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Knowledge Base Page</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="kb-title">Title</Label>
              <Input
                id="kb-title"
                value={title}
                onChange={(e) => handleTitleChange(e.target.value)}
                placeholder="Page title"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kb-slug">Slug</Label>
              <Input
                id="kb-slug"
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                placeholder="my-page-slug"
                className="font-mono text-xs"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kb-folder">Folder</Label>
            <Input
              id="kb-folder"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="/"
            />
          </div>
          <div className="space-y-2">
            <Label>Inject Scope</Label>
            <div className="space-y-2 rounded-md border border-border p-3">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={globalScope}
                  onChange={(e) => setGlobalScope(e.target.checked)}
                  className="rounded"
                />
                <span>Global — inject into all agent contexts</span>
              </label>
              <div className="space-y-1.5">
                <Label htmlFor="kb-roles" className="text-xs text-muted-foreground">
                  Roles (comma-separated)
                </Label>
                <Input
                  id="kb-roles"
                  value={roles}
                  onChange={(e) => setRoles(e.target.value)}
                  placeholder="soc-analyst, incident-responder"
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="kb-agents" className="text-xs text-muted-foreground">
                  Agent UUIDs (comma-separated)
                </Label>
                <Input
                  id="kb-agents"
                  value={agents}
                  onChange={(e) => setAgents(e.target.value)}
                  placeholder="uuid1, uuid2"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kb-body">Content (Markdown)</Label>
            <Textarea
              id="kb-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write markdown content here..."
              className="min-h-48 font-mono text-xs"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createPage.isPending}
          >
            {createPage.isPending ? "Creating..." : "Create Page"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* -------------------------------------------------------------------------- */
/*  Page columns                                                               */
/* -------------------------------------------------------------------------- */

const PAGE_COLUMNS = [
  { key: "title", label: "Title", initialWidth: 280 },
  { key: "folder", label: "Folder", initialWidth: 140 },
  { key: "scope", label: "Scope", initialWidth: 130 },
  { key: "sync", label: "Synced", initialWidth: 120 },
  { key: "rev", label: "Rev", initialWidth: 60 },
  { key: "updated", label: "Updated", initialWidth: 110 },
];

/* -------------------------------------------------------------------------- */
/*  KBPage — main export                                                       */
/* -------------------------------------------------------------------------- */

export function KBPage() {
  const navigate = useNavigate();
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [showNewDialog, setShowNewDialog] = useState(false);

  // Simple debounce via useState + effect pattern
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  function handleSearchChange(v: string) {
    setSearchInput(v);
    if (debounceTimer) clearTimeout(debounceTimer);
    const t = setTimeout(() => setDebouncedQuery(v), 300);
    setDebounceTimer(t);
  }

  const isSearching = debouncedQuery.length >= 1;

  const folders = useKBFolders();
  const pages = useKBPages(
    isSearching
      ? undefined
      : selectedFolder
        ? { folder: selectedFolder }
        : undefined,
  );
  const searchResults = useKBSearch(debouncedQuery);

  function handleFolderSelect(path: string) {
    setSelectedFolder((prev) => (prev === path ? null : path));
    setSearchInput("");
    setDebouncedQuery("");
  }

  function navigateToPage(page: KBPageSummary | KBSearchResult) {
    if ("uuid" in page) {
      void navigate({
        to: "/manage/kb/$uuid",
        params: { uuid: page.uuid },
        search: { slug: page.slug, tab: "content" },
      });
    } else {
      // KBSearchResult has no UUID — we need to find it from the pages list
      // Navigate using slug in a workaround: find matching page from cache
      const match = pages.data?.data.find((p) => p.slug === page.slug);
      if (match) {
        void navigate({
          to: "/manage/kb/$uuid",
          params: { uuid: match.uuid },
          search: { slug: match.slug, tab: "content" },
        });
      }
    }
  }

  const isLoading = isSearching ? searchResults.isLoading : pages.isLoading;

  return (
    <AppLayout title="Knowledge Base">
      <div className="flex h-full min-h-0 gap-0">
        {/* Sidebar */}
        <aside className="w-52 shrink-0 border-r border-border bg-card/50 flex flex-col">
          <div className="px-3 py-3 border-b border-border">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Folders
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {folders.isLoading ? (
              <div className="space-y-1.5 p-1">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : folders.data?.data && folders.data.data.length > 0 ? (
              <>
                <button
                  onClick={() => setSelectedFolder(null)}
                  className={cn(
                    "flex w-full items-center gap-1.5 px-2 py-1.5 rounded-md text-xs transition-colors mb-1",
                    selectedFolder === null && !isSearching
                      ? "bg-teal/15 text-teal"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  <Folder className="h-3.5 w-3.5" />
                  All pages
                </button>
                <FolderTree
                  nodes={folders.data.data}
                  selected={selectedFolder}
                  onSelect={handleFolderSelect}
                />
              </>
            ) : (
              <p className="text-xs text-muted-foreground px-2 py-2">
                No folders yet
              </p>
            )}
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Toolbar */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <h1 className="text-lg font-heading font-extrabold tracking-tight text-foreground shrink-0">
              Knowledge Base
            </h1>
            <div className="flex-1 relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <Input
                value={searchInput}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search pages..."
                className="pl-8 h-8 text-sm"
              />
            </div>
            <Button
              size="sm"
              onClick={() => setShowNewDialog(true)}
              className="gap-1.5 shrink-0"
            >
              <Plus className="h-3.5 w-3.5" />
              New page
            </Button>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="p-4 space-y-2">
                {[...Array(8)].map((_, i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            ) : (
              <ResizableTable storageKey="kb-pages-table" columns={PAGE_COLUMNS}>
                <TableHeader>
                  <TableRow>
                    {PAGE_COLUMNS.map((col) => (
                      <ResizableTableHead key={col.key} columnKey={col.key}>
                        {col.label}
                      </ResizableTableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isSearching ? (
                    <>
                      {searchResults.data?.data.length === 0 && (
                        <TableRow>
                          <TableCell
                            colSpan={PAGE_COLUMNS.length}
                            className="text-center text-sm text-muted-foreground py-12"
                          >
                            No search results for &ldquo;{debouncedQuery}&rdquo;
                          </TableCell>
                        </TableRow>
                      )}
                      {searchResults.data?.data.map((r) => (
                        <SearchResultRow
                          key={r.slug}
                          result={r}
                          onClick={() => navigateToPage(r)}
                        />
                      ))}
                    </>
                  ) : (
                    <>
                      {pages.data?.data.length === 0 && (
                        <TableRow>
                          <TableCell
                            colSpan={PAGE_COLUMNS.length}
                            className="text-center text-sm text-muted-foreground py-12"
                          >
                            No pages{selectedFolder ? ` in ${selectedFolder}` : ""}
                          </TableCell>
                        </TableRow>
                      )}
                      {pages.data?.data.map((p) => (
                        <PageRow
                          key={p.uuid}
                          page={p}
                          onClick={() => navigateToPage(p)}
                        />
                      ))}
                    </>
                  )}
                </TableBody>
              </ResizableTable>
            )}
          </div>
        </div>
      </div>

      <NewPageDialog
        open={showNewDialog}
        onClose={() => setShowNewDialog(false)}
      />
    </AppLayout>
  );
}

/* -------------------------------------------------------------------------- */
/*  Row sub-components                                                         */
/* -------------------------------------------------------------------------- */

function PageRow({
  page,
  onClick,
}: {
  page: KBPageSummary;
  onClick: () => void;
}) {
  return (
    <TableRow
      className="cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={onClick}
    >
      <TableCell className="py-2.5">
        <span className="text-sm font-medium text-foreground truncate block">
          {page.title}
        </span>
        <span className="text-xs text-muted-foreground font-mono truncate block mt-0.5">
          {page.slug}
        </span>
      </TableCell>
      <TableCell className="py-2.5">
        <Badge variant="outline" className="text-xs font-mono">
          {page.folder}
        </Badge>
      </TableCell>
      <TableCell className="py-2.5">
        <InjectScopeBadges scope={page.inject_scope} />
      </TableCell>
      <TableCell className="py-2.5">
        <SyncCell synced_at={page.synced_at} sync_source={page.sync_source} />
      </TableCell>
      <TableCell className="py-2.5 text-xs text-muted-foreground">
        v{page.latest_revision_number}
      </TableCell>
      <TableCell className="py-2.5 text-xs text-muted-foreground">
        {relativeTime(page.updated_at)}
      </TableCell>
    </TableRow>
  );
}

function SearchResultRow({
  result,
  onClick,
}: {
  result: KBSearchResult;
  onClick: () => void;
}) {
  return (
    <TableRow
      className="cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={onClick}
    >
      <TableCell className="py-2.5">
        <span className="text-sm font-medium text-foreground truncate block">
          {result.title}
        </span>
        {result.summary && (
          <span className="text-xs text-muted-foreground truncate block mt-0.5">
            {result.summary}
          </span>
        )}
      </TableCell>
      <TableCell className="py-2.5">
        <Badge variant="outline" className="text-xs font-mono">
          {result.folder}
        </Badge>
      </TableCell>
      <TableCell className="py-2.5">
        <InjectScopeBadges scope={result.inject_scope} />
      </TableCell>
      <TableCell className="py-2.5">
        <span className="text-xs text-muted-foreground">
          {result.sync_source ?? "local"}
        </span>
      </TableCell>
      <TableCell className="py-2.5 text-xs text-muted-foreground">
        {result.relevance_score != null
          ? `${Math.round(result.relevance_score * 100)}%`
          : "—"}
      </TableCell>
      <TableCell className="py-2.5 text-xs text-muted-foreground">
        {relativeTime(result.updated_at)}
      </TableCell>
    </TableRow>
  );
}
