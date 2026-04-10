import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  DndContext,
  DragOverlay,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { Skeleton } from "@/components/ui/skeleton";
import { useKBPages, useKBFolders, useCreateKBPage, usePatchKBPage } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Plus, FileText, Folder } from "lucide-react";
import type { KBFolderNode, KBPageSummary } from "@/lib/types";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\.md$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/* -------------------------------------------------------------------------- */
/*  Draggable page item                                                        */
/* -------------------------------------------------------------------------- */

function DraggablePageItem({
  page,
  selectedSlug,
  onSelect,
  paddingLeft,
}: {
  page: KBPageSummary;
  selectedSlug: string | undefined;
  onSelect: (page: KBPageSummary) => void;
  paddingLeft: number;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `page:${page.slug}`,
    data: { type: "page", page },
  });

  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={() => onSelect(page)}
      className={cn(
        "flex w-full items-center gap-1.5 py-1 text-xs rounded transition-colors",
        isDragging ? "opacity-40" : "",
        selectedSlug === page.slug
          ? "bg-teal/15 text-teal"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
      style={{ paddingLeft }}
      {...attributes}
      {...listeners}
    >
      <FileText className="h-3 w-3 shrink-0" />
      <span className="truncate">{page.title}</span>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Droppable folder item                                                      */
/* -------------------------------------------------------------------------- */

function DroppableFolderItem({
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

  const { setNodeRef, isOver } = useDroppable({
    id: `folder:${node.path}`,
    data: { type: "folder", path: node.path },
  });

  if (!hasContent) {
    // Still render the folder header so it can be a drop target
    return (
      <div>
        <button
          ref={setNodeRef}
          type="button"
          onClick={() => setOpen((o) => !o)}
          className={cn(
            "flex w-full items-center gap-1 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded",
            isOver && "ring-1 ring-teal/60 bg-teal/10",
          )}
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
      </div>
    );
  }

  return (
    <div>
      <button
        ref={setNodeRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center gap-1 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded",
          isOver && "ring-1 ring-teal/60 bg-teal/10",
        )}
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
            <DraggablePageItem
              key={page.uuid}
              page={page}
              selectedSlug={selectedSlug}
              onSelect={onSelect}
              paddingLeft={22 + depth * 12}
            />
          ))}
          {node.children.map((child) => (
            <DroppableFolderItem
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
/*  Droppable root zone                                                        */
/* -------------------------------------------------------------------------- */

function DroppableRoot({ children, isOver }: { children: React.ReactNode; isOver: boolean }) {
  const { setNodeRef } = useDroppable({
    id: "folder:/",
    data: { type: "folder", path: "/" },
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "min-h-4 rounded transition-colors",
        isOver && "ring-1 ring-teal/60 bg-teal/5",
      )}
    >
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Inline filename input                                                      */
/* -------------------------------------------------------------------------- */

function InlineFileInput({
  onConfirm,
  onCancel,
}: {
  onConfirm: (filename: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      const trimmed = value.trim();
      if (trimmed) onConfirm(trimmed);
      else onCancel();
    } else if (e.key === "Escape") {
      onCancel();
    }
  }

  function handleBlur() {
    if (!value.trim()) onCancel();
  }

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 text-xs rounded bg-accent/50">
      <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        placeholder="filename.md"
        className="flex-1 bg-transparent outline-none text-xs text-foreground placeholder:text-muted-foreground/60 min-w-0"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Static drag overlay card                                                   */
/* -------------------------------------------------------------------------- */

function PageDragOverlay({ page }: { page: KBPageSummary }) {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 text-xs rounded bg-background border border-border shadow-md opacity-90 w-48">
      <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="truncate text-foreground">{page.title}</span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  KBSidebar — shared across index and detail                                */
/* -------------------------------------------------------------------------- */

export function KBSidebar({ selectedSlug }: { selectedSlug?: string }) {
  const navigate = useNavigate();
  const allPages = useKBPages({ page_size: 500 });
  const folders = useKBFolders();
  const createPage = useCreateKBPage();
  const patchPage = usePatchKBPage();

  const [showInlineInput, setShowInlineInput] = useState(false);
  const [activeDragPage, setActiveDragPage] = useState<KBPageSummary | null>(null);
  const [overDropId, setOverDropId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const pagesList: KBPageSummary[] = allPages.data?.data ?? [];
  const folderNodes: KBFolderNode[] = folders.data?.data ?? [];

  function handleSelect(page: KBPageSummary) {
    void navigate({
      to: "/kb/$uuid",
      params: { uuid: page.uuid },
      search: { slug: page.slug, tab: "content" },
    });
  }

  const rootPages = pagesList.filter(
    (p) => !folderNodes.some((f) => f.path === p.folder),
  );

  const handleInlineConfirm = useCallback(
    async (filename: string) => {
      setShowInlineInput(false);
      const slug = slugify(filename);
      const title = slug
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
      try {
        const result = await createPage.mutateAsync({
          title,
          slug,
          folder: "/",
          body: "",
        });
        toast.success("Page created");
        void navigate({
          to: "/kb/$uuid",
          params: { uuid: result.data.uuid },
          search: { slug: result.data.slug, tab: "content" },
        });
      } catch {
        toast.error("Failed to create page");
      }
    },
    [createPage, navigate],
  );

  function handleDragStart(event: DragStartEvent) {
    const data = event.active.data.current as { type: string; page: KBPageSummary } | undefined;
    if (data?.type === "page") {
      setActiveDragPage(data.page);
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveDragPage(null);
    setOverDropId(null);

    const { active, over } = event;
    if (!over) return;

    const dragData = active.data.current as { type: string; page: KBPageSummary } | undefined;
    const dropData = over.data.current as { type: string; path: string } | undefined;

    if (dragData?.type !== "page" || dropData?.type !== "folder") return;

    const page = dragData.page;
    const targetFolder = dropData.path;

    if (page.folder === targetFolder) return;

    try {
      await patchPage.mutateAsync({ slug: page.slug, body: { folder: targetFolder } });
      toast.success(`Moved to ${targetFolder === "/" ? "root" : targetFolder}`);
    } catch {
      toast.error("Failed to move page");
    }
  }

  const isRootOver = overDropId === "folder:/";

  return (
    <aside className="w-64 shrink-0 border-r border-border bg-surface flex flex-col">
      {/* Header */}
      <div className="px-3 py-3 border-b border-border flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">Knowledge Base</span>
        <button
          type="button"
          onClick={() => setShowInlineInput(true)}
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
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragOver={(e) => setOverDropId(e.over?.id ? String(e.over.id) : null)}
            onDragEnd={handleDragEnd}
            onDragCancel={() => { setActiveDragPage(null); setOverDropId(null); }}
          >
            {/* Inline input at top */}
            {showInlineInput && (
              <InlineFileInput
                onConfirm={handleInlineConfirm}
                onCancel={() => setShowInlineInput(false)}
              />
            )}

            {pagesList.length === 0 && !showInlineInput ? (
              <div className="px-3 py-4 text-xs text-muted-foreground text-center">
                No pages yet.{" "}
                <button
                  type="button"
                  className="text-teal underline"
                  onClick={() => setShowInlineInput(true)}
                >
                  Create one
                </button>
              </div>
            ) : (
              <>
                {folderNodes.map((node) => (
                  <DroppableFolderItem
                    key={node.path}
                    node={node}
                    pages={pagesList}
                    selectedSlug={selectedSlug}
                    onSelect={handleSelect}
                    depth={0}
                  />
                ))}
                <DroppableRoot isOver={isRootOver}>
                  {rootPages.map((page) => (
                    <DraggablePageItem
                      key={page.uuid}
                      page={page}
                      selectedSlug={selectedSlug}
                      onSelect={handleSelect}
                      paddingLeft={8}
                    />
                  ))}
                </DroppableRoot>
              </>
            )}

            <DragOverlay>
              {activeDragPage ? <PageDragOverlay page={activeDragPage} /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </aside>
  );
}
