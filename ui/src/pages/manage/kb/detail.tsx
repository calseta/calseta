import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
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
import {
  useKBPages,
  useKBFolders,
  useKBPage,
  useCreateKBPage,
  usePatchKBPage,
} from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  FileText,
  Folder,
  ArrowLeft,
  Bold,
  Italic,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Code,
  Undo,
  Redo,
} from "lucide-react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import type { KBFolderNode, KBPageSummary } from "@/lib/types";

/* -------------------------------------------------------------------------- */
/*  Sidebar tree                                                               */
/* -------------------------------------------------------------------------- */

function FolderItem({
  node,
  pages,
  selectedSlug,
  onSelectPage,
  depth,
}: {
  node: KBFolderNode;
  pages: KBPageSummary[];
  selectedSlug: string;
  onSelectPage: (page: KBPageSummary) => void;
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
        className="flex w-full items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded"
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <Folder className="h-3 w-3 shrink-0" />
        <span className="truncate">{node.name}</span>
      </button>
      {open && (
        <div>
          {folderPages.map((page) => (
            <button
              key={page.uuid}
              type="button"
              onClick={() => onSelectPage(page)}
              className={cn(
                "flex w-full items-center gap-1.5 py-1 text-xs rounded transition-colors",
                selectedSlug === page.slug
                  ? "bg-teal/15 text-teal"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
              style={{ paddingLeft: `${20 + depth * 12}px` }}
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
              onSelectPage={onSelectPage}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Toolbar                                                                    */
/* -------------------------------------------------------------------------- */

function ToolbarButton({
  onClick,
  active,
  disabled,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "h-7 w-7 flex items-center justify-center rounded text-xs transition-colors",
        active
          ? "bg-teal/15 text-teal"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
        disabled && "opacity-40 cursor-not-allowed",
      )}
    >
      {children}
    </button>
  );
}

function ToolbarDivider() {
  return <div className="w-px h-4 bg-border mx-1" />;
}

/* -------------------------------------------------------------------------- */
/*  New Page Dialog                                                            */
/* -------------------------------------------------------------------------- */

interface NewPageDialogProps {
  open: boolean;
  onClose: () => void;
  defaultFolder?: string;
}

function NewPageDialog({ open, onClose, defaultFolder = "/" }: NewPageDialogProps) {
  const navigate = useNavigate();
  const createPage = useCreateKBPage();
  const [title, setTitle] = useState("");
  const [folder, setFolder] = useState(defaultFolder);
  const [slugManual, setSlugManual] = useState(false);
  const [slug, setSlug] = useState("");

  function handleTitleChange(v: string) {
    setTitle(v);
    if (!slugManual) {
      setSlug(v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
    }
  }

  async function handleSubmit() {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    const finalSlug = slug.trim() || title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    try {
      const result = await createPage.mutateAsync({
        title: title.trim(),
        slug: finalSlug,
        folder: folder.trim() || "/",
        body: "",
      });
      toast.success("Page created");
      onClose();
      setTitle("");
      setSlug("");
      setSlugManual(false);
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
              onChange={(e) => handleTitleChange(e.target.value)}
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
/*  Main page                                                                  */
/* -------------------------------------------------------------------------- */

export function KBDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { slug } = useSearch({ strict: false }) as { slug?: string };
  const navigate = useNavigate();

  const allPages = useKBPages({ page_size: 500 });
  const folders = useKBFolders();
  const page = useKBPage(slug ?? "");
  const patchPage = usePatchKBPage();

  const [showNewPage, setShowNewPage] = useState(false);
  const [savedIndicator, setSavedIndicator] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pageData = page.data?.data;
  const pagesList: KBPageSummary[] = allPages.data?.data ?? [];
  const folderNodes: KBFolderNode[] = folders.data?.data ?? [];

  // Debounced save
  const debouncedSave = useCallback(
    (content: string) => {
      if (!slug) return;
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      setSavedIndicator("saving");
      saveTimeoutRef.current = setTimeout(() => {
        patchPage.mutate(
          { slug, body: { body: content } },
          {
            onSuccess: () => setSavedIndicator("saved"),
            onError: () => {
              setSavedIndicator("idle");
              toast.error("Failed to save");
            },
          },
        );
      }, 1000);
    },
    [slug, patchPage],
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: "Start writing…" }),
    ],
    content: pageData?.body ?? "",
    onUpdate: ({ editor }) => {
      debouncedSave(editor.getHTML());
      setSavedIndicator("saving");
    },
    editorProps: {
      attributes: {
        class: "kb-editor min-h-[400px] focus:outline-none px-6 py-4 text-sm text-foreground",
      },
    },
  });

  // When page loads or changes, update editor content
  useEffect(() => {
    if (editor && pageData?.body !== undefined) {
      const current = editor.getHTML();
      if (current !== pageData.body) {
        editor.commands.setContent(pageData.body ?? "");
      }
      setSavedIndicator("idle");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageData?.uuid]);

  function handleSelectPage(p: KBPageSummary) {
    void navigate({
      to: "/kb/$uuid",
      params: { uuid: p.uuid },
      search: { slug: p.slug, tab: "content" },
    });
    setSavedIndicator("idle");
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
    <AppLayout title={pageData?.title ?? "Knowledge Base"}>
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 shrink-0 border-r border-border bg-surface flex flex-col">
          {/* Sidebar header */}
          <div className="px-3 py-3 border-b border-border flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigate({ to: "/kb" })}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Knowledge Base
            </button>
            <button
              type="button"
              onClick={() => setShowNewPage(true)}
              title="New page"
              className="h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Page tree */}
          <div className="flex-1 overflow-y-auto py-2 px-1">
            {allPages.isLoading || folders.isLoading ? (
              <div className="space-y-1 px-2">
                {[...Array(6)].map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <>
                {folderNodes.map((node) => (
                  <FolderItem
                    key={node.path}
                    node={node}
                    pages={pagesList}
                    selectedSlug={slug}
                    onSelectPage={handleSelectPage}
                    depth={0}
                  />
                ))}
                {/* Pages without a matching folder node */}
                {pagesList
                  .filter((p) => !folderNodes.some((f) => f.path === p.folder || p.folder === "/"))
                  .map((p) => (
                    <button
                      key={p.uuid}
                      type="button"
                      onClick={() => handleSelectPage(p)}
                      className={cn(
                        "flex w-full items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors",
                        slug === p.slug
                          ? "bg-teal/15 text-teal"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      )}
                    >
                      <FileText className="h-3 w-3 shrink-0" />
                      <span className="truncate">{p.title}</span>
                    </button>
                  ))}
              </>
            )}
          </div>
        </aside>

        {/* Editor pane */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {page.isLoading ? (
            <div className="p-8 space-y-4">
              <Skeleton className="h-7 w-64" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : !pageData ? (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              Page not found.
            </div>
          ) : (
            <>
              {/* Editor header */}
              <div className="px-6 pt-5 pb-3 border-b border-border shrink-0">
                <div className="flex items-center justify-between">
                  <h1 className="text-lg font-semibold text-foreground">{pageData.title}</h1>
                  <span className="text-xs text-muted-foreground">
                    {savedIndicator === "saving" && "Saving…"}
                    {savedIndicator === "saved" && "Saved"}
                  </span>
                </div>
                <p className="text-xs font-mono text-muted-foreground mt-0.5">{pageData.slug}</p>
              </div>

              {/* Toolbar */}
              {editor && !pageData.sync_source && (
                <div className="px-6 py-2 border-b border-border flex items-center gap-0.5 shrink-0 bg-card/50">
                  <ToolbarButton
                    title="Heading 1"
                    active={editor.isActive("heading", { level: 1 })}
                    onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                  >
                    <Heading1 className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Heading 2"
                    active={editor.isActive("heading", { level: 2 })}
                    onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                  >
                    <Heading2 className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Heading 3"
                    active={editor.isActive("heading", { level: 3 })}
                    onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                  >
                    <Heading3 className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarDivider />
                  <ToolbarButton
                    title="Bold"
                    active={editor.isActive("bold")}
                    onClick={() => editor.chain().focus().toggleBold().run()}
                  >
                    <Bold className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Italic"
                    active={editor.isActive("italic")}
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                  >
                    <Italic className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarDivider />
                  <ToolbarButton
                    title="Bullet List"
                    active={editor.isActive("bulletList")}
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                  >
                    <List className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Ordered List"
                    active={editor.isActive("orderedList")}
                    onClick={() => editor.chain().focus().toggleOrderedList().run()}
                  >
                    <ListOrdered className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarDivider />
                  <ToolbarButton
                    title="Blockquote"
                    active={editor.isActive("blockquote")}
                    onClick={() => editor.chain().focus().toggleBlockquote().run()}
                  >
                    <Quote className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Code Block"
                    active={editor.isActive("codeBlock")}
                    onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                  >
                    <Code className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarDivider />
                  <ToolbarButton
                    title="Undo"
                    disabled={!editor.can().undo()}
                    onClick={() => editor.chain().focus().undo().run()}
                  >
                    <Undo className="h-3.5 w-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    title="Redo"
                    disabled={!editor.can().redo()}
                    onClick={() => editor.chain().focus().redo().run()}
                  >
                    <Redo className="h-3.5 w-3.5" />
                  </ToolbarButton>
                </div>
              )}

              {/* Synced page notice */}
              {pageData.sync_source && (
                <div className="px-6 py-2 border-b border-border bg-amber/5 shrink-0">
                  <p className="text-xs text-amber">
                    This page is managed by an external sync source. Edits made here will be overwritten on the next sync.
                  </p>
                </div>
              )}

              {/* Editor */}
              <div className="flex-1 overflow-y-auto">
                <EditorContent editor={editor} />
              </div>
            </>
          )}
        </div>
      </div>

      <NewPageDialog
        open={showNewPage}
        onClose={() => setShowNewPage(false)}
      />
    </AppLayout>
  );
}
