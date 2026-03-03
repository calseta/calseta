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
import { useSources, useCreateSource, useDeleteSource } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { Plus, Trash2 } from "lucide-react";

const SRC_COLUMNS: ColumnDef[] = [
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

export function SourcesPage() {
  const { data, isLoading } = useSources();
  const createSource = useCreateSource();
  const deleteSource = useDeleteSource();
  const [open, setOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);

  const sources = data?.data ?? [];

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

  return (
    <AppLayout title="Source Integrations">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-xs text-dim">{sources.length} sources</span>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Source
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border">
              <DialogHeader>
                <DialogTitle>Add Source Integration</DialogTitle>
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
          <ResizableTable storageKey="sources" columns={SRC_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
                <ResizableTableHead columnKey="display_name" className="text-dim text-xs">Display Name</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Status</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">Created (UTC)</ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 5 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : sources.map((src) => (
                    <TableRow key={src.uuid} className="border-border hover:bg-accent/50">
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
                  ))}
              {!isLoading && sources.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-dim py-12">
                    No source integrations configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </ResizableTable>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Source Integration"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
