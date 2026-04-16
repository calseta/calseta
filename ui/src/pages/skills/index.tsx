import { useState } from "react";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Switch } from "@/components/ui/switch";
import {
  useSkills,
  useSkill,
  useCreateSkill,
  usePatchSkill,
  useDeleteSkill,
  useUpsertSkillFile,
  useDeleteSkillFile,
} from "@/hooks/use-api";
import { DocumentationEditor } from "@/components/detail-page/documentation-editor";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Plus,
  Search,
  Wand2,
  Trash2,
  X,
  Lock,
  FileText,
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  Globe,
} from "lucide-react";
import type { Skill, SkillFile } from "@/lib/types";

function slugify(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
}

function isValidSlug(s: string): boolean {
  return /^[a-z0-9-]+$/.test(s);
}

// ─── File tree builder ────────────────────────────────────────────────────────

type FileNode = { kind: "file"; name: string; file: SkillFile };
type DirNode = { kind: "dir"; name: string; children: TreeNode[] };
type TreeNode = FileNode | DirNode;

function buildTree(files: SkillFile[]): TreeNode[] {
  const root: TreeNode[] = [];

  // Entry file always first
  const entry = files.find((f) => f.is_entry);
  const rest = files.filter((f) => !f.is_entry).sort((a, b) => a.path.localeCompare(b.path));
  const ordered = entry ? [entry, ...rest] : rest;

  for (const file of ordered) {
    const parts = file.path.split("/");
    if (parts.length === 1) {
      root.push({ kind: "file", name: parts[0], file });
    } else {
      let current = root;
      for (let i = 0; i < parts.length - 1; i++) {
        const dirName = parts[i];
        let dir = current.find((n): n is DirNode => n.kind === "dir" && n.name === dirName);
        if (!dir) {
          dir = { kind: "dir", name: dirName, children: [] };
          current.push(dir);
        }
        current = dir.children;
      }
      current.push({ kind: "file", name: parts[parts.length - 1], file });
    }
  }

  return root;
}

// ─── File tree renderer (sidebar) ────────────────────────────────────────────

function FileTreeNodes({
  nodes,
  depth,
  activeFilePath,
  onSelectFile,
}: {
  nodes: TreeNode[];
  depth: number;
  activeFilePath: string;
  onSelectFile: (path: string) => void;
}) {
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(() => {
    // Auto-expand dirs that contain the active file
    const expanded = new Set<string>();
    const toggle = (ns: TreeNode[], prefix: string) => {
      for (const n of ns) {
        if (n.kind === "dir") {
          const key = prefix + n.name;
          const hasActive = (children: TreeNode[]): boolean =>
            children.some((c) =>
              c.kind === "file"
                ? c.file.path === activeFilePath
                : hasActive(c.children),
            );
          if (hasActive(n.children)) expanded.add(key);
          toggle(n.children, key + "/");
        }
      }
    };
    toggle(nodes, "");
    return expanded;
  });

  function toggleDir(key: string) {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  return (
    <>
      {nodes.map((node) => {
        const indentPx = depth * 12;
        if (node.kind === "file") {
          const active = activeFilePath === node.file.path;
          return (
            <button
              key={node.file.uuid}
              onClick={() => onSelectFile(node.file.path)}
              style={{ paddingLeft: `${8 + indentPx}px` }}
              className={cn(
                "w-full flex items-center gap-1.5 py-1 pr-2 rounded text-left transition-colors",
                active
                  ? "bg-teal/15 text-teal-light"
                  : "hover:bg-muted/40 text-foreground",
              )}
            >
              <FileText className="h-3 w-3 shrink-0 text-dim" />
              <span className="text-[11px] font-mono truncate">{node.name}</span>
            </button>
          );
        }

        // dir node
        const key = node.name; // unique within siblings at this level
        const open = expandedDirs.has(depth + key);
        return (
          <div key={node.name}>
            <button
              onClick={() => toggleDir(depth + key)}
              style={{ paddingLeft: `${8 + indentPx}px` }}
              className="w-full flex items-center gap-1.5 py-1 pr-2 rounded text-left hover:bg-muted/40 text-dim transition-colors"
            >
              {open ? (
                <ChevronDown className="h-3 w-3 shrink-0" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0" />
              )}
              {open ? (
                <FolderOpen className="h-3 w-3 shrink-0" />
              ) : (
                <Folder className="h-3 w-3 shrink-0" />
              )}
              <span className="text-[11px] font-mono truncate">{node.name}/</span>
            </button>
            {open && (
              <FileTreeNodes
                nodes={node.children}
                depth={depth + 1}
                activeFilePath={activeFilePath}
                onSelectFile={onSelectFile}
              />
            )}
          </div>
        );
      })}
    </>
  );
}

// ─── Sidebar skill row ────────────────────────────────────────────────────────

function SkillTreeRow({
  skill,
  isExpanded,
  onToggle,
  activeFilePath,
  onSelectFile,
  isSelected,
}: {
  skill: Skill;
  isExpanded: boolean;
  onToggle: () => void;
  activeFilePath: string;
  onSelectFile: (skillUuid: string, filePath: string) => void;
  isSelected: boolean;
}) {
  const files = skill.files ?? [];
  const tree = buildTree(files);
  const [showAddFile, setShowAddFile] = useState(false);
  const upsertFile = useUpsertSkillFile();

  return (
    <div>
      {/* Skill folder row */}
      <div className="group relative">
        <button
          onClick={onToggle}
          className={cn(
            "w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-left transition-colors",
            isSelected
              ? "text-teal-light"
              : "hover:bg-muted/40 text-foreground",
          )}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-dim" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-dim" />
          )}
          {isExpanded ? (
            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-teal" />
          ) : (
            <Folder className="h-3.5 w-3.5 shrink-0 text-dim" />
          )}
          <span className="text-xs font-medium truncate flex-1">{skill.name}</span>
          {skill.is_global && (
            <Globe className="h-3 w-3 text-teal shrink-0" title="Global — injected into all agents" />
          )}
          {!skill.is_active && (
            <Badge
              variant="outline"
              className="text-[9px] text-dim border-dim/30 px-1 py-0 shrink-0"
            >
              off
            </Badge>
          )}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); setShowAddFile(true); }}
          className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity h-4 w-4 flex items-center justify-center rounded hover:bg-muted/60 text-dim hover:text-foreground"
          title="Add file"
        >
          <Plus className="h-3 w-3" />
        </button>
      </div>

      {/* File tree */}
      {isExpanded && (
        <div className="ml-2 border-l border-border/50 pl-1 mb-0.5">
          {files.length === 0 ? (
            <p className="text-[10px] text-dim px-2 py-1">No files</p>
          ) : (
            <FileTreeNodes
              nodes={tree}
              depth={0}
              activeFilePath={isSelected ? activeFilePath : ""}
              onSelectFile={(path) => onSelectFile(skill.uuid, path)}
            />
          )}
        </div>
      )}

      <AddFileDialog
        open={showAddFile}
        onOpenChange={setShowAddFile}
        existingPaths={files.map((f) => f.path)}
        isPending={upsertFile.isPending}
        onAdd={(path) => {
          upsertFile.mutate(
            { skillUuid: skill.uuid, path, content: "" },
            {
              onSuccess: () => {
                toast.success(`${path} added`);
                onSelectFile(skill.uuid, path);
                setShowAddFile(false);
              },
              onError: () => toast.error("Failed to add file"),
            },
          );
        }}
      />
    </div>
  );
}

// ─── New Skill Dialog ─────────────────────────────────────────────────────────

function NewSkillDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isGlobal, setIsGlobal] = useState(false);
  const [slugTouched, setSlugTouched] = useState(false);
  const createSkill = useCreateSkill();

  function handleNameChange(v: string) {
    setName(v);
    if (!slugTouched) setSlug(slugify(v));
  }

  function handleCreate() {
    if (!name.trim()) { toast.error("Name is required"); return; }
    if (!slug.trim()) { toast.error("Slug is required"); return; }
    if (!isValidSlug(slug)) { toast.error("Slug must be lowercase letters, numbers, and hyphens only"); return; }

    createSkill.mutate(
      { slug, name, description: description || null, is_global: isGlobal },
      {
        onSuccess: () => {
          toast.success("Skill created");
          onOpenChange(false);
          setSlug(""); setName(""); setDescription(""); setIsGlobal(false); setSlugTouched(false);
        },
        onError: () => toast.error("Failed to create skill"),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New Skill</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="skill-name">Name *</Label>
            <Input
              id="skill-name"
              placeholder="Triage Runbook"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="skill-slug">
              Slug *
              <span className="ml-1.5 text-[11px] text-dim font-normal">directory: ~/.claude/skills/{slug || "…"}/</span>
            </Label>
            <Input
              id="skill-slug"
              placeholder="triage-runbook"
              value={slug}
              onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); }}
              className={cn(!isValidSlug(slug) && slug ? "border-red-threat" : "")}
            />
            {slug && !isValidSlug(slug) && (
              <p className="text-xs text-red-threat">Lowercase letters, numbers, and hyphens only</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="skill-description">Description</Label>
            <Input
              id="skill-description"
              placeholder="Short summary of what this skill does"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="skill-global"
              checked={isGlobal}
              onCheckedChange={setIsGlobal}
            />
            <Label htmlFor="skill-global" className="text-xs cursor-pointer">
              Global skill <span className="text-dim font-normal">(injected into all agents automatically)</span>
            </Label>
          </div>
          <p className="text-xs text-dim">
            After creating the skill, edit <code className="bg-muted px-1 py-0.5 rounded">SKILL.md</code> in the file editor.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={createSkill.isPending}>
            {createSkill.isPending ? "Creating..." : "Create Skill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Add File Dialog ──────────────────────────────────────────────────────────

function AddFileDialog({
  open,
  onOpenChange,
  existingPaths,
  onAdd,
  isPending,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  existingPaths: string[];
  onAdd: (path: string) => void;
  isPending: boolean;
}) {
  const [path, setPath] = useState("");

  const pathError = (() => {
    if (!path) return null;
    if (!path.endsWith(".md")) return "Path must end in .md";
    if (path === "SKILL.md") return "SKILL.md already exists";
    if (existingPaths.includes(path)) return "A file at this path already exists";
    if (/[^a-zA-Z0-9/_.\-]/.test(path)) return "Only letters, numbers, slashes, dots, underscores, and hyphens";
    return null;
  })();

  function handleSubmit() {
    if (!path || pathError) return;
    onAdd(path);
  }

  function handleClose() {
    setPath("");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Add File</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="file-path">File path</Label>
            <Input
              id="file-path"
              placeholder="references/playbook.md"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              className={cn(pathError ? "border-red-threat" : "")}
              autoFocus
            />
            {pathError && <p className="text-xs text-red-threat">{pathError}</p>}
            <p className="text-[11px] text-dim">Use forward slashes for subdirectories. Must end in .md</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!path || !!pathError || isPending}>
            {isPending ? "Adding..." : "Add File"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Skill Detail Panel ───────────────────────────────────────────────────────

function SkillDetailPanel({
  skillSummary,
  activeFilePath,
  onFileSelect,
  onClose,
}: {
  skillSummary: Skill;
  activeFilePath: string;
  onFileSelect: (path: string) => void;
  onClose: () => void;
}) {
  const { data: skillData, isLoading } = useSkill(skillSummary.uuid);
  const skill = skillData?.data ?? skillSummary;
  const files: SkillFile[] = skill.files ?? [];

  const [name, setName] = useState(skill.name);
  const [description, setDescription] = useState(skill.description ?? "");
  const [isActive, setIsActive] = useState(skill.is_active);
  const [isGlobal, setIsGlobal] = useState(skill.is_global);
  const [showAddFile, setShowAddFile] = useState(false);

  const patchSkill = usePatchSkill();
  const deleteSkill = useDeleteSkill();
  const upsertFile = useUpsertSkillFile();
  const deleteFile = useDeleteSkillFile();

  const sortedFiles = [...files].sort((a, b) => {
    if (a.is_entry) return -1;
    if (b.is_entry) return 1;
    return a.path.localeCompare(b.path);
  });

  const activeFile = sortedFiles.find((f) => f.path === activeFilePath) ?? sortedFiles[0] ?? null;

  function saveMetadata(overrides?: { name?: string; description?: string; is_active?: boolean; is_global?: boolean }) {
    patchSkill.mutate(
      {
        uuid: skill.uuid,
        body: {
          name: overrides?.name ?? name,
          description: (overrides?.description !== undefined ? overrides.description : description) || null,
          is_active: overrides?.is_active !== undefined ? overrides.is_active : isActive,
          is_global: overrides?.is_global !== undefined ? overrides.is_global : isGlobal,
        },
      },
      {
        onSuccess: () => toast.success("Skill saved"),
        onError: () => toast.error("Failed to save skill"),
      },
    );
  }

  function handleDelete() {
    deleteSkill.mutate(skill.uuid, {
      onSuccess: () => { toast.success("Skill deleted"); onClose(); },
      onError: () => toast.error("Failed to delete skill"),
    });
  }

  function handleFileSave(content: string) {
    if (!activeFile) return;
    upsertFile.mutate(
      { skillUuid: skill.uuid, path: activeFile.path, content },
      {
        onSuccess: () => toast.success("File saved"),
        onError: () => toast.error("Failed to save file"),
      },
    );
  }

  function handleAddFile(path: string) {
    upsertFile.mutate(
      { skillUuid: skill.uuid, path, content: "" },
      {
        onSuccess: () => {
          toast.success(`${path} added`);
          onFileSelect(path);
          setShowAddFile(false);
        },
        onError: () => toast.error("Failed to add file"),
      },
    );
  }

  function handleDeleteFile(file: SkillFile) {
    deleteFile.mutate(
      { skillUuid: skill.uuid, fileUuid: file.uuid },
      {
        onSuccess: () => {
          toast.success(`${file.path} deleted`);
          if (activeFilePath === file.path) onFileSelect("SKILL.md");
        },
        onError: () => toast.error("Failed to delete file"),
      },
    );
  }

  function handleCreateEntryFile() {
    upsertFile.mutate(
      { skillUuid: skill.uuid, path: "SKILL.md", content: "" },
      {
        onSuccess: () => { toast.success("SKILL.md created"); onFileSelect("SKILL.md"); },
        onError: () => toast.error("Failed to create SKILL.md"),
      },
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border shrink-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-foreground text-sm truncate">{skill.name}</span>
            <code className="text-[11px] bg-muted px-1.5 py-0.5 rounded text-dim">{skill.slug}/</code>
            <Badge
              variant="outline"
              className={cn(
                "text-[10px]",
                skill.is_active
                  ? "text-teal bg-teal/10 border-teal/30"
                  : "text-dim bg-dim/10 border-dim/30",
              )}
            >
              {skill.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <p className="text-xs text-dim mt-0.5">Updated {formatDate(skill.updated_at)}</p>
        </div>
        <button onClick={onClose} className="text-dim hover:text-foreground transition-colors shrink-0">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => name !== skill.name && saveMetadata({ name })}
              className="text-sm h-8"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Slug (read-only)</Label>
            <code className="flex items-center h-8 px-3 rounded-md border border-border bg-muted text-sm text-dim select-all">
              {skill.slug}
            </code>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Description</Label>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => description !== (skill.description ?? "") && saveMetadata({ description })}
            placeholder="Short description of what this skill does"
            className="text-sm h-8"
          />
        </div>

        <div className="flex items-center gap-3">
          <Label className="text-xs">Active</Label>
          <Switch
            checked={isActive}
            onCheckedChange={(v) => { setIsActive(v); saveMetadata({ is_active: v }); }}
          />
        </div>

        <div className="flex items-center gap-3">
          <Label className="text-xs">Global</Label>
          <Switch
            checked={isGlobal}
            onCheckedChange={(v) => { setIsGlobal(v); saveMetadata({ is_global: v }); }}
          />
          <span className="text-[11px] text-dim">Injected into all agents automatically</span>
        </div>

        {/* File list (compact, for add/delete — tree nav is in sidebar) */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Files</span>
            <Button size="sm" variant="outline" className="h-6 px-2 text-xs gap-1" onClick={() => setShowAddFile(true)}>
              <Plus className="h-3 w-3" />
              Add File
            </Button>
          </div>

          {isLoading ? (
            <div className="space-y-1">
              {[1, 2].map((i) => <Skeleton key={i} className="h-8 w-full rounded-md" />)}
            </div>
          ) : files.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-4 border border-dashed border-border rounded-md">
              <p className="text-xs text-dim">No files found</p>
              <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={handleCreateEntryFile} disabled={upsertFile.isPending}>
                <FileText className="h-3 w-3" />
                Create SKILL.md
              </Button>
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-hidden divide-y divide-border">
              {sortedFiles.map((file) => (
                <div
                  key={file.uuid}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors",
                    activeFile?.path === file.path
                      ? "bg-teal/10 text-teal-light"
                      : "hover:bg-muted/40 text-foreground",
                  )}
                  onClick={() => onFileSelect(file.path)}
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-dim" />
                  <span className="text-xs font-mono flex-1 truncate">{file.path}</span>
                  {file.is_entry ? (
                    <Lock className="h-3 w-3 text-dim shrink-0" title="Entry file — cannot be deleted" />
                  ) : (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="text-dim hover:text-red-threat transition-colors shrink-0"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete file?</AlertDialogTitle>
                          <AlertDialogDescription>
                            Permanently delete <code>{file.path}</code> from <strong>{skill.name}</strong>.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleDeleteFile(file)} className="bg-red-threat hover:bg-red-threat/90">
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Editor */}
        {activeFile ? (
          <DocumentationEditor
            key={activeFile.uuid}
            content={activeFile.content}
            onSave={handleFileSave}
            isSaving={upsertFile.isPending}
            title={`Editing: ${activeFile.path}`}
            rows={20}
          />
        ) : files.length > 0 ? (
          <p className="text-xs text-dim text-center py-4">Select a file to edit</p>
        ) : null}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border shrink-0 flex items-center justify-between">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 text-xs text-red-threat hover:bg-red-threat/10 hover:text-red-threat gap-1.5">
              <Trash2 className="h-3.5 w-3.5" />
              Delete Skill
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete skill?</AlertDialogTitle>
              <AlertDialogDescription>
                Permanently delete <strong>{skill.name}</strong> (<code>{skill.slug}</code>) and all its files.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDelete} className="bg-red-threat hover:bg-red-threat/90">
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <AddFileDialog
        open={showAddFile}
        onOpenChange={setShowAddFile}
        existingPaths={files.map((f) => f.path)}
        onAdd={handleAddFile}
        isPending={upsertFile.isPending}
      />
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function SkillsPage() {
  const [showNew, setShowNew] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(288);
  const [activeFilePath, setActiveFilePath] = useState<string>("SKILL.md");
  const [expandedUuids, setExpandedUuids] = useState<Set<string>>(new Set());

  const { data, isLoading } = useSkills();
  const allSkills = data?.data ?? [];

  const filtered = allSkills.filter(
    (s) =>
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.slug.toLowerCase().includes(search.toLowerCase()),
  );

  const selected = allSkills.find((s) => s.uuid === selectedUuid) ?? null;

  function handleSelectFile(skillUuid: string, filePath: string) {
    setSelectedUuid(skillUuid);
    setActiveFilePath(filePath);
    setExpandedUuids((prev) => new Set([...prev, skillUuid]));
  }

  function handleToggleSkill(uuid: string) {
    setExpandedUuids((prev) => {
      const next = new Set(prev);
      if (next.has(uuid)) {
        next.delete(uuid);
        // Deselect if collapsing the selected skill
        if (selectedUuid === uuid) setSelectedUuid(null);
      } else {
        next.add(uuid);
        // Select skill and default to SKILL.md when expanding
        setSelectedUuid(uuid);
        setActiveFilePath("SKILL.md");
      }
      return next;
    });
  }

  return (
    <AppLayout title="Skills Library">
      <div className="flex gap-0 h-[calc(100vh-7rem)] rounded-lg border border-border overflow-hidden">
        {/* Left sidebar — file explorer */}
        <div className="relative shrink-0 flex flex-col border-r border-border bg-muted/5" style={{ width: sidebarWidth }}>
          {/* Header */}
          <div className="p-3 border-b border-border space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Skills Library</span>
              <Button size="sm" onClick={() => setShowNew(true)} className="h-6 px-2 text-xs gap-1">
                <Plus className="h-3 w-3" />
                New
              </Button>
            </div>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-dim" />
              <Input
                placeholder="Search skills..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-7 h-7 text-xs"
              />
            </div>
          </div>

          {/* Tree */}
          <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-2 py-1.5">
                  <Skeleton className="h-4 w-28" />
                </div>
              ))
            ) : filtered.length === 0 ? (
              <div className="text-center text-xs text-dim py-10">
                {search ? "No skills match your search" : "No skills yet"}
              </div>
            ) : (
              filtered.map((skill) => (
                <SkillTreeRow
                  key={skill.uuid}
                  skill={skill}
                  isExpanded={expandedUuids.has(skill.uuid)}
                  onToggle={() => handleToggleSkill(skill.uuid)}
                  activeFilePath={activeFilePath}
                  onSelectFile={handleSelectFile}
                  isSelected={selectedUuid === skill.uuid}
                />
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-3 py-2 border-t border-border shrink-0">
            <p className="text-[11px] text-dim">
              {allSkills.length} skill{allSkills.length !== 1 ? "s" : ""} total
            </p>
          </div>
          {/* Resize handle */}
          <div
            className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-teal/30 active:bg-teal/50 transition-colors z-10"
            onMouseDown={(e) => {
              e.preventDefault();
              const startX = e.clientX;
              const startWidth = sidebarWidth;
              function onMove(ev: MouseEvent) {
                setSidebarWidth(Math.min(480, Math.max(180, startWidth + ev.clientX - startX)));
              }
              function onUp() {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
              }
              document.addEventListener("mousemove", onMove);
              document.addEventListener("mouseup", onUp);
            }}
          />
        </div>

        {/* Right panel */}
        <div className="flex-1 min-w-0">
          {selected ? (
            <SkillDetailPanel
              key={selected.uuid}
              skillSummary={selected}
              activeFilePath={activeFilePath}
              onFileSelect={setActiveFilePath}
              onClose={() => {
                setSelectedUuid(null);
                setExpandedUuids((prev) => {
                  const next = new Set(prev);
                  next.delete(selected.uuid);
                  return next;
                });
              }}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3">
              <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                <Wand2 className="h-6 w-6 text-dim" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Select a skill to edit</p>
                <p className="text-xs text-dim mt-1">Skills are Markdown file trees injected into agent context</p>
              </div>
              <Button size="sm" onClick={() => setShowNew(true)} className="h-8 gap-1.5 mt-2">
                <Plus className="h-3.5 w-3.5" />
                New Skill
              </Button>
            </div>
          )}
        </div>
      </div>

      <NewSkillDialog open={showNew} onOpenChange={setShowNew} />
    </AppLayout>
  );
}
