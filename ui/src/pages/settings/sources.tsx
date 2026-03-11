import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ResizableTable,
  ResizableTableHead,
  type ColumnDef,
} from "@/components/ui/resizable-table";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { CopyableText } from "@/components/copyable-text";
import { TablePagination } from "@/components/table-pagination";
import { useSources, useCreateSource, useDeleteSource } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { Plus, Trash2, ChevronDown, ChevronRight } from "lucide-react";

const SRC_COLUMNS: ColumnDef[] = [
  { key: "expand", initialWidth: 32, minWidth: 32, maxWidth: 32 },
  { key: "source", initialWidth: 160, minWidth: 100 },
  { key: "display_name", initialWidth: 200, minWidth: 120 },
  { key: "status", initialWidth: 90, minWidth: 70 },
  { key: "created", initialWidth: 160, minWidth: 120 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

const AVAILABLE_SOURCES = [
  { value: "sentinel", label: "Microsoft Sentinel" },
  { value: "elastic", label: "Elastic Security" },
  { value: "splunk", label: "Splunk" },
  { value: "generic", label: "Generic Webhook" },
];

const SOURCE_DOC_SLUGS: Record<string, string> = {
  sentinel: "sentinel",
  elastic: "elastic",
  splunk: "splunk",
  generic: "generic",
};

export function SourcesPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } = useTableState({});
  const { data, isLoading } = useSources(params);
  const createSource = useCreateSource();
  const deleteSource = useDeleteSource();
  const [open, setOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);
  const [expandedSource, setExpandedSource] = useState<string | null>(null);

  const sources = data?.data ?? [];
  const meta = data?.meta;
  const origin = typeof window !== "undefined" ? window.location.origin : "https://your-calseta-host";

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const displayName = fd.get("display_name") as string;
    const sourceInfo = AVAILABLE_SOURCES.find((s) => s.value === selectedSource);

    createSource.mutate(
      {
        source_name: selectedSource,
        display_name: displayName || sourceInfo?.label || selectedSource,
        is_active: true,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setSelectedSource("");
          toast.success("Source integration added");
        },
        onError: () => toast.error("Failed to add source integration"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteSource.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Source integration deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete source integration"),
    });
  }

  function toggleExpand(uuid: string) {
    setExpandedSource((prev) => (prev === uuid ? null : uuid));
  }

  return (
    <AppLayout title="Alert Sources">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-xs text-dim">{meta?.total ?? sources.length} sources</span>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Source
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border">
              <DialogHeader>
                <DialogTitle>Add Alert Source</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">Source Type</Label>
                  <Select value={selectedSource} onValueChange={setSelectedSource} required>
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue placeholder="Select a source..." />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {AVAILABLE_SOURCES.map((src) => (
                        <SelectItem key={src.value} value={src.value}>
                          {src.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Display Name</Label>
                  <Input name="display_name" className="mt-1 bg-surface border-border text-sm" placeholder="Optional custom display name" />
                </div>
                <Button type="submit" disabled={createSource.isPending || !selectedSource} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="alert-sources" columns={SRC_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="expand" className="text-dim text-xs w-8" />
                <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
                <ResizableTableHead columnKey="display_name" className="text-dim text-xs">Display Name</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Status</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">Created</ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 6 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : sources.map((src) => (
                    <>
                      <TableRow key={src.uuid} className="border-border hover:bg-accent/50">
                        <TableCell className="w-8 p-0 pl-2">
                          <button
                            onClick={() => toggleExpand(src.uuid)}
                            className="p-1 text-dim hover:text-foreground"
                          >
                            {expandedSource === src.uuid ? (
                              <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </TableCell>
                        <TableCell className="text-sm font-mono text-foreground">{src.source_name}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{src.display_name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={src.is_active ? "text-teal bg-teal/10 border-teal/30 text-[11px]" : "text-dim bg-dim/10 border-dim/30 text-[11px]"}>
                            {src.is_active ? "active" : "inactive"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(src.created_at)}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTarget({ uuid: src.uuid, name: src.display_name })}
                            className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedSource === src.uuid && (
                        <TableRow key={`${src.uuid}-detail`} className="border-border bg-surface/50">
                          <TableCell colSpan={6}>
                            <div className="py-3 px-2 space-y-3">
                              <div>
                                <span className="text-[11px] text-dim uppercase tracking-wider font-medium">Webhook URL</span>
                                <div className="mt-1">
                                  <CopyableText
                                    text={`${origin}/v1/alerts/ingest/${src.source_name}`}
                                    mono
                                    className="text-xs text-teal"
                                  />
                                </div>
                              </div>
                              <div>
                                <span className="text-[11px] text-dim uppercase tracking-wider font-medium">Required Headers</span>
                                <div className="mt-1 space-y-1">
                                  <div className="flex items-center gap-2">
                                    <code className="text-xs text-dim bg-surface px-1.5 py-0.5 rounded border border-border">Authorization: Bearer cai_...</code>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <code className="text-xs text-dim bg-surface px-1.5 py-0.5 rounded border border-border">Content-Type: application/json</code>
                                  </div>
                                </div>
                              </div>
                              {SOURCE_DOC_SLUGS[src.source_name] && (
                                <a
                                  href={`https://docs.calseta.com/integrations/alert-sources/${SOURCE_DOC_SLUGS[src.source_name]}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs text-teal hover:underline"
                                >
                                  View full setup guide &rarr;
                                </a>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  ))}
              {!isLoading && sources.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-dim py-12">
                    No alert sources configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </ResizableTable>
        </div>

        {meta && (
          <TablePagination
            page={page}
            pageSize={pageSize}
            totalPages={meta.total_pages}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Alert Source"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
