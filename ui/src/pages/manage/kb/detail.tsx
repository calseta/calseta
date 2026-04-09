import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useSearch } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Skeleton } from "@/components/ui/skeleton";
import { useKBPage, usePatchKBPage } from "@/hooks/use-api";
import { MarkdownPreview } from "@/components/markdown-preview";
import { cn } from "@/lib/utils";
import {
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
  Eye,
  Pencil,
} from "lucide-react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { KBSidebar } from "./sidebar";

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
/*  KBDetailPage                                                               */
/* -------------------------------------------------------------------------- */

export function KBDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { slug } = useSearch({ strict: false }) as { slug?: string };

  const page = useKBPage(slug ?? "");
  const patchPage = usePatchKBPage();

  const [isPreview, setIsPreview] = useState(false);
  const [savedIndicator, setSavedIndicator] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pageData = page.data?.data;

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
    },
    editorProps: {
      attributes: {
        class: "kb-editor min-h-[400px] focus:outline-none px-6 py-4 text-sm text-foreground",
      },
    },
  });

  // Reload content when navigating between pages
  useEffect(() => {
    if (editor && pageData?.body !== undefined) {
      const current = editor.getHTML();
      if (current !== pageData.body) {
        editor.commands.setContent(pageData.body ?? "");
      }
      setSavedIndicator("idle");
      setIsPreview(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageData?.uuid]);

  if (!slug) {
    return (
      <AppLayout title="Knowledge Base">
        <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
          <KBSidebar />
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
            Invalid page reference — no slug provided.
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title={pageData?.title ?? "Knowledge Base"}>
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
        <KBSidebar selectedSlug={slug} />

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
              {/* Page header */}
              <div className="px-6 pt-5 pb-3 border-b border-border shrink-0">
                <div className="flex items-center justify-between">
                  <h1 className="text-lg font-semibold text-foreground">{pageData.title}</h1>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {savedIndicator === "saving" && "Saving…"}
                      {savedIndicator === "saved" && "Saved"}
                    </span>
                    {/* Edit / Preview toggle */}
                    {!pageData.sync_source && (
                      <div className="flex items-center border border-border rounded-md overflow-hidden">
                        <button
                          type="button"
                          onClick={() => setIsPreview(false)}
                          className={cn(
                            "flex items-center gap-1 px-2.5 py-1 text-xs transition-colors",
                            !isPreview
                              ? "bg-teal/15 text-teal"
                              : "text-muted-foreground hover:bg-accent",
                          )}
                        >
                          <Pencil className="h-3 w-3" />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsPreview(true)}
                          className={cn(
                            "flex items-center gap-1 px-2.5 py-1 text-xs border-l border-border transition-colors",
                            isPreview
                              ? "bg-teal/15 text-teal"
                              : "text-muted-foreground hover:bg-accent",
                          )}
                        >
                          <Eye className="h-3 w-3" />
                          Preview
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <p className="text-xs font-mono text-muted-foreground mt-0.5">{pageData.slug}</p>
              </div>

              {/* Toolbar (edit mode only) */}
              {!isPreview && editor && !pageData.sync_source && (
                <div className="px-6 py-2 border-b border-border flex items-center gap-0.5 shrink-0 bg-card/50 flex-wrap">
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

              {/* Sync notice */}
              {pageData.sync_source && (
                <div className="px-6 py-2 border-b border-border bg-amber/5 shrink-0">
                  <p className="text-xs text-amber">
                    This page is managed by an external sync source. Edits made here will be overwritten on the next sync.
                  </p>
                </div>
              )}

              {/* Content area */}
              <div className="flex-1 overflow-y-auto">
                {isPreview ? (
                  <div className="px-6 py-4">
                    {pageData.body ? (
                      <MarkdownPreview content={pageData.body} />
                    ) : (
                      <p className="text-sm text-muted-foreground italic">No content yet.</p>
                    )}
                  </div>
                ) : (
                  <EditorContent editor={editor} />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
