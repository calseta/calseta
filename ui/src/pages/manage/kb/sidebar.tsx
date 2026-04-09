import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useKBPages, useKBFolders, useCreateKBPage } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Plus, FileText, Folder } from "lucide-react";
import type { KBFolderNode, KBPageSummary } from "@/lib/types";

/* -------------------------------------------------------------------------- */
/*  Folder tree item                                                           */
/* -------------------------------------------------------------------------- */

function FolderItem({
  node,
  pages,
  selectedSlug,
  onSelect,
  depth,
}: {
  node: KBFolderNode;
  pages: KBPageSummary[];
  selectedSlug: string | undefined;
  onSelect: (page: KBPageSummary) => void;
  depth: number;
}) {
  const [open, setOpen] = useState(true);
  const folderPages = pages.filter((p) => p.folder === node.path);
  const hasContent = folderPages.length > 0 || node.children.length > 0;

  if (!hasContent) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded"
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <Folder className="h-3 w-3 shrink-0" />
        <span className="truncate font-medium">{node.name}</span>
      </button>
      {open && (
        <div>
          {folderPages.map((page) => (
            <button
              key={page.uuid}
              type="button"
              onClick={() => onSelect(page)}
              className={cn(
                "flex w-full items-center gap-1.5 py-1 text-xs rounded transition-colors",
                selectedSlug === page.slug
                  ? "bg-teal/15 text-teal"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
              style={{ paddingLeft: `${22 + depth * 12}px` }}
            >
              <FileText className="h-3 w-3 shrink-0" />
              <span className="truncate">{page.title}</span>
            </button>
          ))}
          {node.children.map((child) => (
            <FolderItem
              key={child.path}
              node={child}
              pages={pages}
              selectedSlug={selectedSlug}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  New Page Dialog                                                            */
/* -------------------------------------------------------------------------- */

function NewPageDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const createPage = useCreateKBPage();
  const [title, setTitle] = useState("");
  const [folder, setFolder] = useState("/");

  async function handleSubmit() {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    try {
      const result = await createPage.mutateAsync({
        title: title.trim(),
        slug,
        folder: folder.trim() || "/",
        body: "",
      });
      toast.success("Page created");
      setTitle("");
      setFolder("/");
      onClose();
      void navigate({
        to: "/kb/$uuid",
        params: { uuid: result.data.uuid },
        search: { slug: result.data.slug, tab: "content" },
      });
    } catch {
      toast.error("Failed to create page");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New Page</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label>Title</Label>
            <Input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Page title"
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Folder</Label>
            <Input
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="/"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={createPage.isPending || !title.trim()}
            className="bg-teal text-white hover:bg-teal-dim"
          >
            {createPage.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* -------------------------------------------------------------------------- */
/*  KBSidebar — shared across index and detail                                */
/* -------------------------------------------------------------------------- */

export function KBSidebar({ selectedSlug }: { selectedSlug?: string }) {
  const navigate = useNavigate();
  const allPages = useKBPages({ page_size: 500 });
  const folders = useKBFolders();
  const [showNewPage, setShowNewPage] = useState(false);

  const pagesList: KBPageSummary[] = allPages.data?.data ?? [];
  const folderNodes: KBFolderNode[] = folders.data?.data ?? [];

  function handleSelect(page: KBPageSummary) {
    void navigate({
      to: "/kb/$uuid",
      params: { uuid: page.uuid },
      search: { slug: page.slug, tab: "content" },
    });
  }

  // Pages that don't fall under any folder node (root-level pages)
  const rootPages = pagesList.filter(
    (p) => !folderNodes.some((f) => f.path === p.folder),
  );

  return (
    <>
      <aside className="w-64 shrink-0 border-r border-border bg-surface flex flex-col">
        {/* Header */}
        <div className="px-3 py-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground">Knowledge Base</span>
          <button
            type="button"
            onClick={() => setShowNewPage(true)}
            title="New page"
            className="h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto py-2 px-1">
          {allPages.isLoading || folders.isLoading ? (
            <div className="space-y-1 px-2">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          ) : pagesList.length === 0 ? (
            <div className="px-3 py-4 text-xs text-muted-foreground text-center">
              No pages yet.{" "}
              <button
                type="button"
                className="text-teal underline"
                onClick={() => setShowNewPage(true)}
              >
                Create one
              </button>
            </div>
          ) : (
            <>
              {folderNodes.map((node) => (
                <FolderItem
                  key={node.path}
                  node={node}
                  pages={pagesList}
                  selectedSlug={selectedSlug}
                  onSelect={handleSelect}
                  depth={0}
                />
              ))}
              {rootPages.map((page) => (
                <button
                  key={page.uuid}
                  type="button"
                  onClick={() => handleSelect(page)}
                  className={cn(
                    "flex w-full items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors",
                    selectedSlug === page.slug
                      ? "bg-teal/15 text-teal"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <FileText className="h-3 w-3 shrink-0" />
                  <span className="truncate">{page.title}</span>
                </button>
              ))}
            </>
          )}
        </div>
      </aside>

      <NewPageDialog open={showNewPage} onClose={() => setShowNewPage(false)} />
    </>
  );
}
