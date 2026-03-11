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
import {
  useIndicatorMappings,
  useCreateIndicatorMapping,
  useDeleteIndicatorMapping,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { Plus, Trash2, Lock } from "lucide-react";

const COLUMNS: ColumnDef[] = [
  { key: "source", initialWidth: 120, minWidth: 80 },
  { key: "target", initialWidth: 110, minWidth: 80 },
  { key: "field_path", initialWidth: 220, minWidth: 120 },
  { key: "indicator_type", initialWidth: 110, minWidth: 80 },
  { key: "system", initialWidth: 70, minWidth: 60 },
  { key: "status", initialWidth: 70, minWidth: 60 },
  { key: "created", initialWidth: 140, minWidth: 100 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

import { INDICATOR_TYPES } from "@/lib/types";
const EXTRACTION_TARGETS = [
  { value: "normalized", label: "Normalized" },
  { value: "raw_payload", label: "Raw Payload" },
];
const SOURCE_OPTIONS = ["sentinel", "elastic", "splunk", "generic"];

export function IndicatorMappingsPage() {
  const { data, isLoading } = useIndicatorMappings({ page_size: 200 });
  const createMapping = useCreateIndicatorMapping();
  const deleteMapping = useDeleteIndicatorMapping();
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; path: string } | null>(null);

  // Form state
  const [formSource, setFormSource] = useState<string>("__all__");
  const [formTarget, setFormTarget] = useState("normalized");
  const [formType, setFormType] = useState("");

  const mappings = data?.data ?? [];

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const fieldPath = (fd.get("field_path") as string).trim();
    const description = (fd.get("description") as string)?.trim() || undefined;

    createMapping.mutate(
      {
        source_name: formSource === "__all__" ? null : formSource,
        extraction_target: formTarget,
        field_path: fieldPath,
        indicator_type: formType,
        is_active: true,
        description,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setFormSource("__all__");
          setFormTarget("normalized");
          setFormType("");
          toast.success("Indicator mapping created");
        },
        onError: () => toast.error("Failed to create indicator mapping"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteMapping.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Indicator mapping deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete indicator mapping"),
    });
  }

  return (
    <AppLayout title="Indicator Mappings">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <span className="text-xs text-dim">{mappings.length} mappings</span>
            <p className="text-[11px] text-dim mt-0.5">
              Define how IOCs are extracted from alert payloads. System mappings apply to all sources.
            </p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Mapping
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border">
              <DialogHeader>
                <DialogTitle>Add Indicator Mapping</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">Source (optional — blank = all sources)</Label>
                  <Select value={formSource} onValueChange={setFormSource}>
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue placeholder="All sources" />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      <SelectItem value="__all__">All sources</SelectItem>
                      {SOURCE_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Extract From</Label>
                  <Select value={formTarget} onValueChange={setFormTarget} required>
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {EXTRACTION_TARGETS.map((t) => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-dim mt-1">
                    {formTarget === "normalized"
                      ? "Match against standardized alert fields (applies to all sources)"
                      : "Match against source-specific raw JSON (use dot-notation paths)"}
                  </p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Field Path</Label>
                  <Input
                    name="field_path"
                    required
                    className="mt-1 bg-surface border-border text-sm font-mono"
                    placeholder="e.g. src_ip or okta.data.client.ipAddress"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Indicator Type</Label>
                  <Select value={formType} onValueChange={setFormType} required>
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue placeholder="Select type..." />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {INDICATOR_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Description (optional)</Label>
                  <Input
                    name="description"
                    className="mt-1 bg-surface border-border text-sm"
                    placeholder="Human-readable description"
                  />
                </div>
                <Button
                  type="submit"
                  disabled={createMapping.isPending || !formType}
                  className="w-full bg-teal text-white hover:bg-teal-dim"
                >
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="indicator-mappings" columns={COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
                <ResizableTableHead columnKey="target" className="text-dim text-xs">Extract From</ResizableTableHead>
                <ResizableTableHead columnKey="field_path" className="text-dim text-xs">Field Path</ResizableTableHead>
                <ResizableTableHead columnKey="indicator_type" className="text-dim text-xs">Indicator Type</ResizableTableHead>
                <ResizableTableHead columnKey="system" className="text-dim text-xs">System</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Active</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">Created</ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 8 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : mappings.map((m) => (
                    <TableRow
                      key={m.uuid}
                      className={`border-border hover:bg-accent/50 ${m.is_system ? "opacity-70" : ""}`}
                    >
                      <TableCell className="text-xs text-foreground font-mono">
                        {m.source_name || <span className="text-dim italic">all</span>}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[10px] ${
                            m.extraction_target === "normalized"
                              ? "text-teal bg-teal/10 border-teal/30"
                              : "text-amber bg-amber/10 border-amber/30"
                          }`}
                        >
                          {m.extraction_target}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-foreground font-mono">{m.field_path}</TableCell>
                      <TableCell className="text-xs text-foreground font-mono">{m.indicator_type}</TableCell>
                      <TableCell>
                        {m.is_system ? (
                          <Lock className="h-3 w-3 text-dim" />
                        ) : (
                          <span className="text-xs text-dim">custom</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[10px] ${
                            m.is_active
                              ? "text-teal bg-teal/10 border-teal/30"
                              : "text-dim bg-dim/10 border-dim/30"
                          }`}
                        >
                          {m.is_active ? "yes" : "no"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(m.created_at)}</TableCell>
                      <TableCell>
                        {!m.is_system && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTarget({ uuid: m.uuid, path: m.field_path })}
                            className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && mappings.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-dim py-12">
                    No indicator mappings configured
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
        title="Delete Indicator Mapping"
        description={`Are you sure you want to delete the mapping for "${deleteTarget?.path}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
