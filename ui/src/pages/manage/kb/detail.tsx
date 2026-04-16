import { useState, useCallback, useEffect, useRef, KeyboardEvent } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import { useKBPageByUUID, usePatchKBPageByUUID, useDeleteKBPageByUUID } from "@/hooks/use-api";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  Bold,
  Italic,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  MoreHorizontal,
  Quote,
  Code,
  Trash2,
  Undo,
  Redo,
  Eye,
  Pencil,
  X,
  Plus,
  Target,
} from "lucide-react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { KBSidebar } from "./sidebar";
import {
  TargetingRuleBuilder,
  TargetingRuleDisplay,
} from "@/components/targeting-rules/targeting-rule-builder";
import {
  type TargetingRules,
  parseTargetingRules,
  serializeTargetingRules,
} from "@/components/targeting-rules/types";

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
/*  Scope types                                                                */
/* -------------------------------------------------------------------------- */

type ScopeMode = "none" | "global" | "per_agent";

function parseScopeMode(inject_scope: Record<string, unknown> | null): ScopeMode {
  if (!inject_scope) return "none";
  if (inject_scope.global === true) return "global";
  return "per_agent";
}

function buildInjectScope(mode: ScopeMode): Record<string, unknown> | null {
  if (mode === "none") return null;
  if (mode === "global") return { global: true };
  return { agent_uuids: [] };
}

/* -------------------------------------------------------------------------- */
/*  TagInput                                                                   */
/* -------------------------------------------------------------------------- */

function TagInput({
  tags,
  onChange,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
}) {
  const [input, setInput] = useState("");

  function addTag(raw: string) {
    const tag = raw.trim();
    if (!tag || tags.includes(tag)) return;
    onChange([...tags, tag]);
    setInput("");
  }

  function removeTag(tag: string) {
    onChange(tags.filter((t) => t !== tag));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag(input);
    }
    if (e.key === "Backspace" && !input && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    }
  }

  return (
    <div className="flex items-center flex-wrap gap-1 min-h-[28px]">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] bg-teal/10 text-teal border border-teal/25"
        >
          {tag}
          <button
            type="button"
            onClick={() => removeTag(tag)}
            className="ml-0.5 text-teal/60 hover:text-teal transition-colors"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => addTag(input)}
        placeholder={tags.length === 0 ? "Add tag…" : "+"}
        className="text-xs bg-transparent outline-none text-foreground placeholder:text-dim min-w-[60px] w-auto"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  KBDetailPage                                                               */
/* -------------------------------------------------------------------------- */

export function KBDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const navigate = useNavigate();

  const page = useKBPageByUUID(uuid);
  const patchPage = usePatchKBPageByUUID();
  const deletePage = useDeleteKBPageByUUID();

  const [isPreview, setIsPreview] = useState(false);
  const [savedIndicator, setSavedIndicator] = useState<"idle" | "saving" | "saved">("idle");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [editingSlug, setEditingSlug] = useState(false);
  const [slugDraft, setSlugDraft] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Metadata local state
  const [descriptionDraft, setDescriptionDraft] = useState<string>("");
  const [tags, setTags] = useState<string[]>([]);
  const [scopeMode, setScopeMode] = useState<ScopeMode>("none");
  const [targetingMode, setTargetingMode] = useState<"none" | "with_rules">("none");
  const [draftRules, setDraftRules] = useState<TargetingRules | null>(null);
  const [showRulesDialog, setShowRulesDialog] = useState(false);

  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pageData = page.data?.data;

  // Sync metadata from server data
  useEffect(() => {
    if (!pageData) return;
    setDescriptionDraft((pageData as Record<string, unknown>).description as string ?? "");
    setTags(((pageData as Record<string, unknown>).tags as string[]) ?? []);
    const scope = parseScopeMode(pageData.inject_scope);
    setScopeMode(scope);
    const rawRules = (pageData as Record<string, unknown>).targeting_rules as Record<string, unknown> | null;
    const parsed = parseTargetingRules(rawRules);
    setTargetingMode(parsed ? "with_rules" : "none");
    setDraftRules(parsed);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageData?.uuid]);

  // Debounced save for editor body
  const debouncedSave = useCallback(
    (content: string) => {
      if (!uuid) return;
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      setSavedIndicator("saving");
      saveTimeoutRef.current = setTimeout(() => {
        patchPage.mutate(
          { uuid, body: { body: content } },
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
    [uuid, patchPage],
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
      setEditingTitle(false);
      setEditingSlug(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageData?.uuid]);

  // Patch helpers
  function patchMeta(body: Record<string, unknown>) {
    if (!uuid) return;
    patchPage.mutate(
      { uuid, body },
      { onError: () => toast.error("Failed to save") },
    );
  }

  function handleDescriptionBlur() {
    const current = (pageData as Record<string, unknown> | undefined)?.description as string ?? "";
    if (descriptionDraft !== current) {
      patchMeta({ description: descriptionDraft });
    }
  }

  function handleTagsChange(newTags: string[]) {
    setTags(newTags);
    patchMeta({ tags: newTags });
  }

  function handleScopeChange(mode: ScopeMode) {
    setScopeMode(mode);
    patchMeta({ inject_scope: buildInjectScope(mode) });
  }

  function handleTargetingModeChange(mode: "none" | "with_rules") {
    setTargetingMode(mode);
    if (mode === "none") {
      setDraftRules(null);
      patchMeta({ targeting_rules: null });
    } else {
      setShowRulesDialog(true);
    }
  }

  function handleSaveRules() {
    const serialized = serializeTargetingRules(draftRules);
    patchPage.mutate(
      { uuid, body: { targeting_rules: serialized ?? null } },
      {
        onSuccess: () => {
          toast.success("Targeting rules saved");
          setShowRulesDialog(false);
        },
        onError: () => toast.error("Failed to save targeting rules"),
      },
    );
  }

  function openRulesDialog() {
    const rawRules = (pageData as Record<string, unknown> | undefined)?.targeting_rules as Record<string, unknown> | null;
    setDraftRules(parseTargetingRules(rawRules));
    setShowRulesDialog(true);
  }

  if (!uuid) {
    return (
      <AppLayout title="Knowledge Base">
        <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
          <KBSidebar />
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
            Invalid page reference.
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title={pageData?.title ?? "Knowledge Base"}>
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
        <KBSidebar selectedUuid={uuid} />

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
              {/* ── Page header ─────────────────────────────────────────── */}
              <div className="px-6 pt-5 pb-3 border-b border-border shrink-0">
                <div className="flex items-center justify-between">
                  {editingTitle ? (
                    <Input
                      autoFocus
                      value={titleDraft}
                      onChange={(e) => setTitleDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const trimmed = titleDraft.trim();
                          if (trimmed && trimmed !== pageData.title) {
                            patchPage.mutate({ uuid, body: { title: trimmed } }, {
                              onSuccess: () => toast.success("Renamed"),
                              onError: () => toast.error("Failed to rename"),
                            });
                          }
                          setEditingTitle(false);
                        }
                        if (e.key === "Escape") setEditingTitle(false);
                      }}
                      onBlur={() => {
                        const trimmed = titleDraft.trim();
                        if (trimmed && trimmed !== pageData.title) {
                          patchPage.mutate({ uuid, body: { title: trimmed } }, {
                            onSuccess: () => toast.success("Renamed"),
                            onError: () => toast.error("Failed to rename"),
                          });
                        }
                        setEditingTitle(false);
                      }}
                      className="text-lg font-semibold h-auto py-0.5 px-1 border-0 border-b border-teal rounded-none bg-transparent focus-visible:ring-0 focus-visible:border-teal w-72"
                    />
                  ) : (
                    <h1
                      className="text-lg font-semibold text-foreground cursor-pointer hover:text-teal transition-colors"
                      onClick={() => { setTitleDraft(pageData.title); setEditingTitle(true); }}
                      title="Click to rename"
                    >
                      {pageData.title}
                    </h1>
                  )}
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
                    {/* Kebab menu (only for non-synced pages) */}
                    {!pageData.sync_source && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-dim hover:text-foreground">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="bg-card border-border">
                          <DropdownMenuItem
                            onClick={() => setShowDeleteConfirm(true)}
                            className="text-red-threat focus:text-red-threat focus:bg-red-threat/10 cursor-pointer"
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-2" />
                            Delete Page
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </div>

                {/* Slug */}
                {editingSlug ? (
                  <input
                    autoFocus
                    value={slugDraft}
                    onChange={(e) => setSlugDraft(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const trimmed = slugDraft.trim().replace(/-+$/, "");
                        if (trimmed && trimmed !== pageData.slug) {
                          patchPage.mutate({ uuid, body: { slug: trimmed } }, {
                            onSuccess: () => {
                              toast.success("Filename renamed");
                              void navigate({ to: "/kb/$uuid", params: { uuid }, search: { tab: "content" } });
                            },
                            onError: () => toast.error("Failed to rename"),
                          });
                        }
                        setEditingSlug(false);
                      }
                      if (e.key === "Escape") setEditingSlug(false);
                    }}
                    onBlur={() => {
                      const trimmed = slugDraft.trim().replace(/-+$/, "");
                      if (trimmed && trimmed !== pageData.slug) {
                        patchPage.mutate({ uuid, body: { slug: trimmed } }, {
                          onSuccess: () => {
                            toast.success("Filename renamed");
                            void navigate({ to: "/kb/$uuid", params: { uuid }, search: { tab: "content" } });
                          },
                          onError: () => toast.error("Failed to rename"),
                        });
                      }
                      setEditingSlug(false);
                    }}
                    className="text-xs font-mono text-muted-foreground mt-0.5 bg-transparent border-0 border-b border-teal outline-none w-48"
                  />
                ) : (
                  <p
                    className="text-xs font-mono text-muted-foreground mt-0.5 cursor-pointer hover:text-teal transition-colors inline-block"
                    onClick={() => { setSlugDraft(pageData.slug); setEditingSlug(true); }}
                    title="Click to rename filename"
                  >
                    {pageData.slug}.md
                  </p>
                )}
              </div>

              {/* ── Metadata section ─────────────────────────────────────── */}
              <div className="px-6 py-3 border-b border-border shrink-0 space-y-2.5">
                {/* Description */}
                <div className="flex items-start gap-3">
                  <span className="micro-label w-24 shrink-0 pt-0.5">Description</span>
                  <input
                    value={descriptionDraft}
                    onChange={(e) => setDescriptionDraft(e.target.value)}
                    onBlur={handleDescriptionBlur}
                    placeholder="Add a description…"
                    className="flex-1 text-xs text-foreground placeholder:text-dim bg-transparent outline-none border-b border-transparent hover:border-border focus:border-teal transition-colors py-0.5"
                  />
                </div>

                {/* Tags */}
                <div className="flex items-start gap-3">
                  <span className="micro-label w-24 shrink-0 pt-0.5">Tags</span>
                  <div className="flex-1">
                    <TagInput tags={tags} onChange={handleTagsChange} />
                  </div>
                </div>

                {/* Scope */}
                <div className="flex items-center gap-3">
                  <span className="micro-label w-24 shrink-0">Scope</span>
                  <Select value={scopeMode} onValueChange={(v) => handleScopeChange(v as ScopeMode)}>
                    <SelectTrigger className="h-6 text-xs border-border bg-transparent w-36 focus:ring-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      <SelectItem value="none" className="text-xs">None</SelectItem>
                      <SelectItem value="global" className="text-xs">Global</SelectItem>
                      <SelectItem value="per_agent" className="text-xs">Per-Agent</SelectItem>
                    </SelectContent>
                  </Select>
                  {scopeMode === "global" && (
                    <span className="text-[11px] text-dim">Injected into all agent contexts</span>
                  )}
                  {scopeMode === "per_agent" && (
                    <span className="text-[11px] text-dim italic">Agent selector coming soon</span>
                  )}
                </div>

                {/* Alert targeting */}
                <div className="flex items-center gap-3">
                  <span className="micro-label w-24 shrink-0">Alert targeting</span>
                  <Select
                    value={targetingMode}
                    onValueChange={(v) => handleTargetingModeChange(v as "none" | "with_rules")}
                  >
                    <SelectTrigger className="h-6 text-xs border-border bg-transparent w-36 focus:ring-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      <SelectItem value="none" className="text-xs">None</SelectItem>
                      <SelectItem value="with_rules" className="text-xs">With rules</SelectItem>
                    </SelectContent>
                  </Select>
                  {targetingMode === "with_rules" && draftRules && (
                    <button
                      type="button"
                      onClick={openRulesDialog}
                      className="flex items-center gap-1 text-[11px] text-teal hover:text-teal-dim transition-colors"
                    >
                      <Target className="h-3 w-3" />
                      {(draftRules.match_any.length + draftRules.match_all.length)} rule
                      {(draftRules.match_any.length + draftRules.match_all.length) !== 1 ? "s" : ""} — Edit
                    </button>
                  )}
                  {targetingMode === "with_rules" && !draftRules && (
                    <button
                      type="button"
                      onClick={openRulesDialog}
                      className="flex items-center gap-1 text-[11px] text-teal hover:text-teal-dim transition-colors"
                    >
                      <Plus className="h-3 w-3" />
                      Add rules
                    </button>
                  )}
                </div>
              </div>

              {/* ── Toolbar (edit mode only) ─────────────────────────────── */}
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

              {/* ── Content area ─────────────────────────────────────────── */}
              <div className="flex-1 overflow-y-auto">
                {isPreview ? (
                  <div className="px-6 py-4">
                    {pageData.body ? (
                      <div
                        className="markdown-preview text-sm"
                        dangerouslySetInnerHTML={{ __html: pageData.body }}
                      />
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

      {/* ── Targeting rules dialog ───────────────────────────────────── */}
      <Dialog open={showRulesDialog} onOpenChange={(v) => { if (!v) setShowRulesDialog(false); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Alert Targeting Rules</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <TargetingRuleBuilder value={draftRules} onChange={setDraftRules} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRulesDialog(false)} disabled={patchPage.isPending}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveRules}
              disabled={patchPage.isPending}
              className="bg-teal text-white hover:bg-teal-dim"
            >
              {patchPage.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete confirm ───────────────────────────────────────────── */}
      {uuid && (
        <ConfirmDialog
          open={showDeleteConfirm}
          onOpenChange={setShowDeleteConfirm}
          title="Delete KB Page"
          description={`Are you sure you want to delete "${pageData?.title ?? "this page"}"? This action cannot be undone.`}
          confirmLabel="Delete"
          variant="destructive"
          onConfirm={() => {
            deletePage.mutate(uuid, {
              onSuccess: () => {
                toast.success("Page deleted");
                navigate({ to: "/kb" });
              },
              onError: () => toast.error("Failed to delete page"),
            });
          }}
        />
      )}
    </AppLayout>
  );
}
