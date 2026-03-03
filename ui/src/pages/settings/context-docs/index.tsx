import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useContextDocuments,
  useCreateContextDocument,
  useDeleteContextDocument,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { CopyableText } from "@/components/copyable-text";
import { Plus, Trash2, FileText, BookOpen, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { TargetingRuleBuilder } from "@/components/targeting-rules/targeting-rule-builder";
import { type TargetingRules, serializeTargetingRules } from "@/components/targeting-rules/types";

export function ContextDocsPage() {
  const { data, isLoading, refetch, isFetching } = useContextDocuments({ page_size: 100 });
  const createDoc = useCreateContextDocument();
  const deleteDoc = useDeleteContextDocument();
  const [open, setOpen] = useState(false);
  const [isGlobal, setIsGlobal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; title: string } | null>(null);
  const [targetingRules, setTargetingRules] = useState<TargetingRules | null>(null);

  const docs = data?.data ?? [];

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const tagsRaw = (fd.get("tags") as string).trim();

    const serializedRules = isGlobal ? undefined : serializeTargetingRules(targetingRules);
    createDoc.mutate(
      {
        title: fd.get("title") as string,
        document_type: (fd.get("document_type") as string) || "runbook",
        content: fd.get("content") as string,
        description: (fd.get("description") as string) || undefined,
        is_global: isGlobal,
        tags: tagsRaw ? tagsRaw.split(",").map((s) => s.trim()) : [],
        ...(serializedRules ? { targeting_rules: serializedRules } : {}),
      },
      {
        onSuccess: () => {
          setOpen(false);
          setIsGlobal(false);
          setTargetingRules(null);
          toast.success("Context document created");
        },
        onError: () => toast.error("Failed to create context document"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteDoc.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Context document deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete context document"),
    });
  }

  return (
    <AppLayout title="Context Documents">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            <span className="text-xs text-dim">{docs.length} documents</span>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Document
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-2xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Context Document</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">Title</Label>
                  <Input name="title" required className="mt-1 bg-surface border-border text-sm" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Description</Label>
                  <Input name="description" className="mt-1 bg-surface border-border text-sm" placeholder="Optional short description" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Type</Label>
                  <Input
                    name="document_type"
                    placeholder="runbook, sop, ir_plan, playbook, detection_guide, other"
                    className="mt-1 bg-surface border-border text-sm"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Tags</Label>
                  <Input name="tags" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: phishing, ransomware, incident" />
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={isGlobal} onCheckedChange={(v) => { setIsGlobal(v); if (v) setTargetingRules(null); }} />
                  <Label className="text-xs text-muted-foreground">Global document (applies to all alerts)</Label>
                </div>
                {!isGlobal && (
                  <div className="rounded-lg border border-border bg-surface p-3">
                    <Label className="text-xs text-muted-foreground mb-2 block">Targeting Rules</Label>
                    <TargetingRuleBuilder value={targetingRules} onChange={setTargetingRules} />
                  </div>
                )}
                <div>
                  <Label className="text-xs text-muted-foreground">Content</Label>
                  <Textarea
                    name="content"
                    required
                    rows={8}
                    className="mt-1 bg-surface border-border text-sm font-mono"
                    placeholder="Paste markdown content..."
                  />
                </div>
                <Button
                  type="submit"
                  disabled={createDoc.isPending}
                  className="w-full bg-teal text-white hover:bg-teal-dim"
                >
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Title</TableHead>
                <TableHead className="text-dim text-xs">UUID</TableHead>
                <TableHead className="text-dim text-xs">Type</TableHead>
                <TableHead className="text-dim text-xs">Scope</TableHead>
                <TableHead className="text-dim text-xs">Tags</TableHead>
                <TableHead className="text-dim text-xs">Version</TableHead>
                <TableHead className="text-dim text-xs">Updated (UTC)</TableHead>
                <TableHead className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 8 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : docs.map((doc) => (
                    <TableRow key={doc.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          to="/settings/context-docs/$uuid"
                          params={{ uuid: doc.uuid }}
                          className="flex items-center gap-2 text-sm text-foreground hover:text-teal-light transition-colors"
                        >
                          {doc.document_type === "runbook" ? (
                            <BookOpen className="h-3.5 w-3.5 text-teal shrink-0" />
                          ) : (
                            <FileText className="h-3.5 w-3.5 text-teal shrink-0" />
                          )}
                          {doc.title}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <CopyableText text={doc.uuid} mono className="text-[11px] text-dim" />
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[11px] text-dim border-border">
                          {doc.document_type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[11px] ${doc.is_global ? "text-amber bg-amber/10 border-amber/30" : "text-dim border-border"}`}>
                          {doc.is_global ? "global" : "targeted"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {doc.tags?.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {doc.tags.map((tag) => (
                              <Badge key={tag} variant="outline" className="text-[10px] text-dim border-border font-normal">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-dim">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-dim font-mono">v{doc.version}</TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(doc.updated_at)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget({ uuid: doc.uuid, title: doc.title })}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && docs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-dim py-12">
                    No context documents yet
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Context Document"
        description={`Are you sure you want to delete "${deleteTarget?.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
