import { useState, useEffect, useRef } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownPreview } from "@/components/markdown-preview";
import {
  useKBPage,
  useCreateKBPage,
  usePatchKBPage,
} from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ArrowLeft, Eye, Save, Bold, Italic, Heading2, List, Code2, Link2 } from "lucide-react";
import { Link } from "@tanstack/react-router";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

interface InjectScopeState {
  global: boolean;
  roles: string; // comma-separated
  agents: string; // comma-separated UUIDs
}

function buildInjectScope(
  scope: InjectScopeState,
): Record<string, unknown> | null {
  const rolesArray = scope.roles
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const agentsArray = scope.agents
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!scope.global && rolesArray.length === 0 && agentsArray.length === 0) {
    return null;
  }
  return {
    ...(scope.global ? { global: true } : {}),
    ...(rolesArray.length > 0 ? { roles: rolesArray } : {}),
    ...(agentsArray.length > 0 ? { agent_uuids: agentsArray } : {}),
  };
}

function parseScopeFromRecord(
  record: Record<string, unknown> | null,
): InjectScopeState {
  if (!record) return { global: false, roles: "", agents: "" };
  return {
    global: !!record.global,
    roles: Array.isArray(record.roles) ? record.roles.join(", ") : "",
    agents: Array.isArray(record.agent_uuids)
      ? record.agent_uuids.join(", ")
      : "",
  };
}

/* -------------------------------------------------------------------------- */
/*  KBEditorPage                                                               */
/* -------------------------------------------------------------------------- */

export function KBEditorPage() {
  const { uuid } = useParams({ strict: false }) as { uuid?: string };
  const { slug } = useSearch({ strict: false }) as { slug?: string };
  const navigate = useNavigate();

  const isEditing = !!slug;

  const existingPage = useKBPage(slug ?? "");
  const createPage = useCreateKBPage();
  const patchPage = usePatchKBPage();

  // Form state
  const [title, setTitle] = useState("");
  const [pageSlug, setPageSlug] = useState("");
  const [folder, setFolder] = useState("/");
  const [body, setBody] = useState("");
  const [injectScope, setInjectScope] = useState<InjectScopeState>({
    global: false,
    roles: "",
    agents: "",
  });
  const [injectPriority, setInjectPriority] = useState(0);
  const [injectPinned, setInjectPinned] = useState(false);
  const [changeSummary, setChangeSummary] = useState("");
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function wrapSelection(before: string, after: string) {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = body.slice(start, end);
    const newBody = body.slice(0, start) + before + selected + after + body.slice(end);
    setBody(newBody);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + before.length, start + before.length + selected.length);
    });
  }

  function prependToLines(prefix: string) {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const beforeSelection = body.slice(0, start);
    const selection = body.slice(start, end) || "";
    const lineStart = beforeSelection.lastIndexOf("\n") + 1;
    const lines = body.slice(lineStart, end === start ? end : end).split("\n");
    const newLines = lines.map((l) => prefix + l);
    const newBody = body.slice(0, lineStart) + newLines.join("\n") + body.slice(end === start ? end : end);
    setBody(newBody);
    requestAnimationFrame(() => {
      el.focus();
    });
  }

  // Prefill when editing
  useEffect(() => {
    if (isEditing && existingPage.data?.data && !initialized) {
      const p = existingPage.data.data;
      setTitle(p.title);
      setPageSlug(p.slug);
      setFolder(p.folder);
      setBody(p.body);
      setInjectScope(parseScopeFromRecord(p.inject_scope));
      setInjectPriority(p.inject_priority);
      setInjectPinned(p.inject_pinned);
      setSlugManuallyEdited(true); // lock slug when editing
      setInitialized(true);
    }
  }, [isEditing, existingPage.data, initialized]);

  function handleTitleChange(v: string) {
    setTitle(v);
    if (!slugManuallyEdited) {
      setPageSlug(
        v
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, ""),
      );
    }
  }

  function handleSlugChange(v: string) {
    setPageSlug(v);
    setSlugManuallyEdited(true);
  }

  function updateScope(field: keyof InjectScopeState, value: boolean | string) {
    setInjectScope((prev) => ({ ...prev, [field]: value }));
  }

  const isSaving = createPage.isPending || patchPage.isPending;

  async function handleSave() {
    if (!title.trim() || !pageSlug.trim()) {
      toast.error("Title and slug are required");
      return;
    }

    try {
      if (isEditing && slug) {
        const patchBody: Record<string, unknown> = {
          title: title.trim(),
          folder: folder.trim() || "/",
          body,
          inject_scope: buildInjectScope(injectScope),
          inject_priority: injectPriority,
          inject_pinned: injectPinned,
        };
        if (changeSummary.trim()) {
          patchBody.change_summary = changeSummary.trim();
        }
        await patchPage.mutateAsync({ slug, body: patchBody });
        toast.success("Page saved");
        void navigate({
          to: "/kb/$uuid",
          params: { uuid: uuid ?? existingPage.data?.data.uuid ?? "" },
          search: { slug, tab: "content" },
        });
      } else {
        const result = await createPage.mutateAsync({
          title: title.trim(),
          slug: pageSlug.trim(),
          folder: folder.trim() || "/",
          body,
          inject_scope: buildInjectScope(injectScope),
          inject_priority: injectPriority,
          inject_pinned: injectPinned,
        });
        toast.success("Page created");
        void navigate({
          to: "/kb/$uuid",
          params: { uuid: result.data.uuid },
          search: { slug: result.data.slug, tab: "content" },
        });
      }
    } catch {
      toast.error(isEditing ? "Failed to save changes" : "Failed to create page");
    }
  }

  const isLoading = isEditing && existingPage.isLoading;
  const backTo = isEditing && uuid
    ? { to: "/kb/$uuid" as const, params: { uuid }, search: { slug: slug ?? "", tab: "content" } }
    : { to: "/kb" as const };

  return (
    <AppLayout title={uuid ? "Edit KB Page" : "New KB Page"}>
      <div className="flex flex-col h-full min-h-0">
        {/* Header bar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/50 shrink-0">
          <Link {...backTo}>
            <ArrowLeft className="h-4 w-4 text-muted-foreground hover:text-foreground transition-colors" />
          </Link>
          <span className="text-sm font-medium text-foreground">
            {isEditing ? "Edit page" : "New page"}
          </span>
          {isEditing && existingPage.data?.data && (
            <Badge variant="outline" className="text-xs font-mono">
              {existingPage.data.data.slug}
            </Badge>
          )}
          <div className="flex-1" />
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Eye className="h-3.5 w-3.5" />
            <span>Live preview</span>
          </div>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={isSaving || isLoading}
            className="gap-1.5"
          >
            <Save className="h-3.5 w-3.5" />
            {isSaving ? "Saving..." : isEditing ? "Save changes" : "Create page"}
          </Button>
        </div>

        {/* Editor + preview split */}
        {isLoading ? (
          <div className="flex-1 p-6 space-y-3">
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-hidden">
            <div className="grid grid-cols-2 gap-0 h-full">
              {/* Left: form + editor */}
              <div className="flex flex-col gap-0 overflow-y-auto border-r border-border">
                {/* Metadata fields */}
                <div className="p-4 space-y-3 border-b border-border bg-card/30">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="editor-title" className="text-xs">
                        Title <span className="text-red-500">*</span>
                      </Label>
                      <Input
                        id="editor-title"
                        value={title}
                        onChange={(e) => handleTitleChange(e.target.value)}
                        placeholder="Page title"
                        className="h-8 text-sm"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="editor-slug" className="text-xs">
                        Slug <span className="text-red-500">*</span>
                        {isEditing && (
                          <span className="ml-1 text-muted-foreground">
                            (read-only)
                          </span>
                        )}
                      </Label>
                      <Input
                        id="editor-slug"
                        value={pageSlug}
                        onChange={(e) => handleSlugChange(e.target.value)}
                        placeholder="my-page-slug"
                        readOnly={isEditing}
                        className={cn(
                          "h-8 text-xs font-mono",
                          isEditing && "opacity-60 cursor-not-allowed",
                        )}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="editor-folder" className="text-xs">
                        Folder
                      </Label>
                      <Input
                        id="editor-folder"
                        value={folder}
                        onChange={(e) => setFolder(e.target.value)}
                        placeholder="/"
                        className="h-8 text-sm font-mono"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="editor-priority" className="text-xs">
                        Inject Priority
                      </Label>
                      <Input
                        id="editor-priority"
                        type="number"
                        min={0}
                        max={100}
                        value={injectPriority}
                        onChange={(e) =>
                          setInjectPriority(Number(e.target.value))
                        }
                        className="h-8 text-sm"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs">Inject Scope</Label>
                    <div className="rounded-md border border-border p-3 space-y-2 bg-background">
                      <label className="flex items-center gap-2 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          checked={injectScope.global}
                          onChange={(e) =>
                            updateScope("global", e.target.checked)
                          }
                          className="rounded"
                        />
                        <span>Global</span>
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] text-muted-foreground">
                            Roles (comma-sep)
                          </Label>
                          <Input
                            value={injectScope.roles}
                            onChange={(e) =>
                              updateScope("roles", e.target.value)
                            }
                            placeholder="soc-analyst, admin"
                            className="h-7 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] text-muted-foreground">
                            Agent UUIDs (comma-sep)
                          </Label>
                          <Input
                            value={injectScope.agents}
                            onChange={(e) =>
                              updateScope("agents", e.target.value)
                            }
                            placeholder="uuid1, uuid2"
                            className="h-7 text-xs font-mono"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={injectPinned}
                        onChange={(e) => setInjectPinned(e.target.checked)}
                        className="rounded"
                      />
                      <span>Pinned (always inject)</span>
                    </label>
                  </div>
                  {isEditing && (
                    <div className="space-y-1.5">
                      <Label htmlFor="editor-summary" className="text-xs">
                        Change summary{" "}
                        <span className="text-muted-foreground">(optional)</span>
                      </Label>
                      <Input
                        id="editor-summary"
                        value={changeSummary}
                        onChange={(e) => setChangeSummary(e.target.value)}
                        placeholder="Describe what changed..."
                        className="h-8 text-sm"
                      />
                    </div>
                  )}
                </div>

                {/* Markdown body textarea */}
                <div className="flex-1 p-4">
                  <Label
                    htmlFor="editor-body"
                    className="text-xs mb-1.5 block"
                  >
                    Content (Markdown)
                  </Label>
                  {/* Formatting toolbar */}
                  <TooltipProvider>
                    <div className="flex items-center gap-0.5 px-1 py-1 border border-b-0 border-border bg-muted/20 rounded-t-md">
                      {[
                        { icon: <Bold className="h-3.5 w-3.5" />, label: "Bold", action: () => wrapSelection("**", "**") },
                        { icon: <Italic className="h-3.5 w-3.5" />, label: "Italic", action: () => wrapSelection("*", "*") },
                        { icon: <Heading2 className="h-3.5 w-3.5" />, label: "Heading", action: () => prependToLines("## ") },
                        { icon: <List className="h-3.5 w-3.5" />, label: "Bullet list", action: () => prependToLines("- ") },
                        { icon: <Code2 className="h-3.5 w-3.5" />, label: "Code block", action: () => wrapSelection("```\n", "\n```") },
                        { icon: <Link2 className="h-3.5 w-3.5" />, label: "Link", action: () => wrapSelection("[", "](url)") },
                      ].map(({ icon, label, action }) => (
                        <Tooltip key={label}>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onMouseDown={(e) => { e.preventDefault(); action(); }}
                              className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            >
                              {icon}
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="text-xs">{label}</TooltipContent>
                        </Tooltip>
                      ))}
                    </div>
                  </TooltipProvider>
                  <Textarea
                    ref={textareaRef}
                    id="editor-body"
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="Write your markdown content here..."
                    className="w-full min-h-[400px] resize-none font-mono text-xs leading-relaxed rounded-t-none"
                    style={{ height: "calc(100vh - 460px)", minHeight: "300px" }}
                  />
                </div>
              </div>

              {/* Right: live preview */}
              <div className="overflow-y-auto bg-card">
                <div className="px-4 py-3 border-b border-border bg-muted/20 flex items-center gap-1.5">
                  <Eye className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground font-medium">
                    Preview
                  </span>
                  {title && (
                    <span className="text-xs text-foreground font-semibold ml-2">
                      {title}
                    </span>
                  )}
                </div>
                <div className="p-6">
                  {body ? (
                    <MarkdownPreview content={body} />
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 gap-2">
                      <Eye className="h-8 w-8 text-muted-foreground/30" />
                      <p className="text-sm text-muted-foreground">
                        Start typing to see a live preview
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
