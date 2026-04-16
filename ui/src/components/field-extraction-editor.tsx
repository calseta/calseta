import { useState, useMemo, useCallback } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  useFieldExtractions,
  useCreateFieldExtraction,
  usePatchFieldExtraction,
  useDeleteFieldExtraction,
  useBulkCreateFieldExtractions,
} from "@/hooks/use-api";
import type { EnrichmentFieldExtraction } from "@/lib/types";
import {
  ArrowRight,
  Lock,
  Plus,
  Trash2,
  X,
  Check,
  Loader2,
  Layers,
  Save,
  Pencil,
} from "lucide-react";

const VALUE_TYPES = ["string", "int", "float", "bool", "list", "dict", "any"];

// Grid: Type(90px) | SourcePath(flex) | arrow(24px) | TargetKey(flex) | ValueType(80px) | Active(48px) | Actions(36px)
const GRID_COLS = "grid-cols-[90px_1fr_24px_1fr_80px_48px_36px]";

interface FieldExtractionEditorProps {
  providerName: string;
  supportedIndicatorTypes: string[];
  isBuiltin: boolean;
}

interface NewRow {
  indicator_type: string;
  source_path: string;
  target_key: string;
  value_type: string;
  description: string;
}

interface EditingRow {
  source_path: string;
  target_key: string;
  value_type: string;
  description: string;
}

const emptyRow = (defaultType: string): NewRow => ({
  indicator_type: defaultType,
  source_path: "",
  target_key: "",
  value_type: "string",
  description: "",
});

export function FieldExtractionEditor({
  providerName,
  supportedIndicatorTypes,
}: FieldExtractionEditorProps) {
  const { data, isLoading } = useFieldExtractions({
    provider_name: providerName,
    page_size: 500,
  });
  const createExtraction = useCreateFieldExtraction();
  const bulkCreate = useBulkCreateFieldExtractions();
  const patchExtraction = usePatchFieldExtraction();
  const deleteExtraction = useDeleteFieldExtraction();

  const [newRows, setNewRows] = useState<NewRow[]>([]);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    uuid: string;
    label: string;
  } | null>(null);

  // Inline editing state for existing rows
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<EditingRow | null>(null);

  const extractions = data?.data ?? [];

  // Group by indicator_type
  const grouped = useMemo(() => {
    const groups: Record<string, EnrichmentFieldExtraction[]> = {};
    for (const ext of extractions) {
      if (!groups[ext.indicator_type]) {
        groups[ext.indicator_type] = [];
      }
      groups[ext.indicator_type].push(ext);
    }
    const sortedKeys = Object.keys(groups).sort((a, b) => {
      const aIdx = supportedIndicatorTypes.indexOf(a);
      const bIdx = supportedIndicatorTypes.indexOf(b);
      if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
      if (aIdx !== -1) return -1;
      if (bIdx !== -1) return 1;
      return a.localeCompare(b);
    });
    return sortedKeys.map((key) => ({
      indicatorType: key,
      items: groups[key],
    }));
  }, [extractions, supportedIndicatorTypes]);

  function addNewRow() {
    setNewRows((prev) => [
      ...prev,
      emptyRow(supportedIndicatorTypes[0] ?? "ip"),
    ]);
  }

  function updateNewRow(index: number, field: keyof NewRow, value: string) {
    setNewRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );
  }

  function removeNewRow(index: number) {
    setNewRows((prev) => prev.filter((_, i) => i !== index));
  }

  const validateRow = useCallback(
    (row: NewRow) => row.source_path.trim() !== "" && row.target_key.trim() !== "",
    [],
  );

  function saveNewRow(index: number) {
    const row = newRows[index];
    if (!validateRow(row)) {
      toast.error("Source path and target key are required");
      return;
    }
    setSavingIndex(index);
    createExtraction.mutate(
      {
        provider_name: providerName,
        indicator_type: row.indicator_type,
        source_path: row.source_path.trim(),
        target_key: row.target_key.trim(),
        value_type: row.value_type,
        description: row.description.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success("Field extraction created");
          removeNewRow(index);
          setSavingIndex(null);
        },
        onError: () => {
          toast.error("Failed to create field extraction");
          setSavingIndex(null);
        },
      },
    );
  }

  function saveAllNewRows() {
    const valid = newRows.every(validateRow);
    if (!valid) {
      toast.error("All rows must have source path and target key");
      return;
    }
    bulkCreate.mutate(
      {
        extractions: newRows.map((row) => ({
          provider_name: providerName,
          indicator_type: row.indicator_type,
          source_path: row.source_path.trim(),
          target_key: row.target_key.trim(),
          value_type: row.value_type,
          description: row.description.trim() || null,
        })),
      },
      {
        onSuccess: () => {
          toast.success(`${newRows.length} field extractions created`);
          setNewRows([]);
        },
        onError: () => toast.error("Failed to create field extractions"),
      },
    );
  }

  function handleToggleActive(extraction: EnrichmentFieldExtraction) {
    patchExtraction.mutate(
      { uuid: extraction.uuid, body: { is_active: !extraction.is_active } },
      {
        onSuccess: () =>
          toast.success(
            `Extraction ${extraction.is_active ? "disabled" : "enabled"}`,
          ),
        onError: () => toast.error("Failed to update extraction"),
      },
    );
  }

  // --- Inline editing ---
  function startEditing(ext: EnrichmentFieldExtraction) {
    setEditingUuid(ext.uuid);
    setEditingDraft({
      source_path: ext.source_path,
      target_key: ext.target_key,
      value_type: ext.value_type,
      description: ext.description ?? "",
    });
  }

  function cancelEditing() {
    setEditingUuid(null);
    setEditingDraft(null);
  }

  function saveEditing(ext: EnrichmentFieldExtraction) {
    if (!editingDraft) return;
    if (!editingDraft.source_path.trim() || !editingDraft.target_key.trim()) {
      toast.error("Source path and target key are required");
      return;
    }

    // Only send changed fields
    const updates: Record<string, unknown> = {};
    if (editingDraft.source_path.trim() !== ext.source_path)
      updates.source_path = editingDraft.source_path.trim();
    if (editingDraft.target_key.trim() !== ext.target_key)
      updates.target_key = editingDraft.target_key.trim();
    if (editingDraft.value_type !== ext.value_type)
      updates.value_type = editingDraft.value_type;
    if ((editingDraft.description.trim() || null) !== (ext.description ?? null))
      updates.description = editingDraft.description.trim() || null;

    if (Object.keys(updates).length === 0) {
      cancelEditing();
      return;
    }

    patchExtraction.mutate(
      { uuid: ext.uuid, body: updates },
      {
        onSuccess: () => {
          toast.success("Extraction updated");
          cancelEditing();
        },
        onError: () => toast.error("Failed to update extraction"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteExtraction.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Field extraction deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete field extraction"),
    });
  }

  if (isLoading) {
    return (
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-foreground">
            <div className="flex items-center gap-2">
              <Layers className="h-3.5 w-3.5 text-teal" />
              Field Extractions
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-foreground">
            <div className="flex items-center gap-2">
              <Layers className="h-3.5 w-3.5 text-teal" />
              Field Extractions
              <Badge
                variant="outline"
                className="text-[11px] text-dim border-border"
              >
                {extractions.length}
              </Badge>
            </div>
          </CardTitle>
          <div className="flex items-center gap-2">
            {newRows.length > 1 && (
              <Button
                size="sm"
                onClick={saveAllNewRows}
                disabled={bulkCreate.isPending}
                className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
              >
                {bulkCreate.isPending ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3 w-3 mr-1" />
                )}
                Save All ({newRows.length})
              </Button>
            )}
            <Button
              size="sm"
              onClick={addNewRow}
              className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Row
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-dim mb-1">
            Map fields from raw enrichment API responses to structured keys
            surfaced to agents. System extractions are locked but can be toggled
            on/off.
          </p>
          <p className="text-[11px] text-dim mb-3">
            <strong>Source path</strong> uses dot-notation into the raw API response body.
            For example, if the response is{" "}
            <code className="text-[11px] bg-surface px-1 py-0.5 rounded border border-border">
              {`{"data": {"attributes": {"reputation": 0}}}`}
            </code>
            , the source path is{" "}
            <code className="text-[11px] bg-surface px-1 py-0.5 rounded border border-border text-teal-light">
              data.attributes.reputation
            </code>.
          </p>

          {/* Table */}
          <div className="rounded-md border border-border overflow-hidden">
            {/* Table header */}
            <div
              className={cn(
                "grid gap-2 bg-surface px-3 py-2 border-b border-border",
                GRID_COLS,
              )}
            >
              <div className="micro-label">Type</div>
              <div className="micro-label">Source Path</div>
              <div />
              <div className="micro-label">Target Key</div>
              <div className="micro-label">Value Type</div>
              <div className="micro-label text-center">Active</div>
              <div />
            </div>

            {/* Empty state */}
            {grouped.length === 0 && newRows.length === 0 && (
              <div className="text-center text-sm text-dim py-8">
                No field extractions configured.
              </div>
            )}

            {/* Existing extractions grouped by indicator type */}
            {grouped.map(({ indicatorType, items }) => (
              <div key={indicatorType}>
                {/* Group separator */}
                <div className="px-3 py-1.5 bg-surface/50 border-b border-border flex items-center gap-2">
                  <span className="text-xs font-mono font-medium text-foreground">
                    {indicatorType}
                  </span>
                  <Badge
                    variant="outline"
                    className="text-[10px] text-dim border-border"
                  >
                    {items.filter((e) => e.is_active).length}/{items.length}
                  </Badge>
                </div>

                {/* Rows */}
                {items.map((ext) => {
                  const isEditing = editingUuid === ext.uuid;

                  if (isEditing && editingDraft) {
                    return (
                      <div
                        key={ext.uuid}
                        className="border-b border-teal/20 bg-teal/5 last:border-b-0"
                      >
                        <div
                          className={cn(
                            "grid gap-2 items-center px-3 py-1.5",
                            GRID_COLS,
                          )}
                        >
                          {/* Type (not editable) */}
                          <span className="text-xs font-mono text-dim truncate">
                            {ext.indicator_type}
                          </span>

                          {/* Source Path */}
                          <Input
                            value={editingDraft.source_path}
                            onChange={(e) =>
                              setEditingDraft({ ...editingDraft, source_path: e.target.value })
                            }
                            className="h-7 bg-surface border-border text-xs font-mono"
                          />

                          {/* Arrow */}
                          <div className="flex justify-center">
                            <ArrowRight className="h-3 w-3 text-dim flex-shrink-0" />
                          </div>

                          {/* Target Key */}
                          <Input
                            value={editingDraft.target_key}
                            onChange={(e) =>
                              setEditingDraft({ ...editingDraft, target_key: e.target.value })
                            }
                            className="h-7 bg-surface border-border text-xs font-mono"
                          />

                          {/* Value Type */}
                          <Select
                            value={editingDraft.value_type}
                            onValueChange={(v) =>
                              setEditingDraft({ ...editingDraft, value_type: v })
                            }
                          >
                            <SelectTrigger className="h-7 bg-surface border-border text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-card border-border">
                              {VALUE_TYPES.map((type) => (
                                <SelectItem key={type} value={type} className="text-xs">
                                  {type}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>

                          {/* Save */}
                          <div className="flex justify-center">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => saveEditing(ext)}
                              disabled={patchExtraction.isPending}
                              className="h-6 w-6 p-0 text-teal hover:text-teal-light"
                              title="Save changes"
                            >
                              {patchExtraction.isPending ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Check className="h-3.5 w-3.5" />
                              )}
                            </Button>
                          </div>

                          {/* Cancel */}
                          <div className="flex justify-center">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={cancelEditing}
                              className="h-6 w-6 p-0 text-dim hover:text-red-threat"
                              title="Cancel editing"
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>

                        {/* Description input row */}
                        <div
                          className={cn(
                            "grid gap-2 items-center px-3 pb-2 pt-0",
                            GRID_COLS,
                          )}
                        >
                          <div />
                          <div className="col-span-3">
                            <Input
                              value={editingDraft.description}
                              onChange={(e) =>
                                setEditingDraft({ ...editingDraft, description: e.target.value })
                              }
                              placeholder="Description (optional)"
                              className="h-6 bg-surface border-border text-[11px] text-dim"
                            />
                          </div>
                          <div />
                          <div />
                          <div />
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={ext.uuid}
                      className={cn(
                        "group border-b border-border last:border-b-0 hover:bg-surface/30 transition-colors",
                        !ext.is_active && "opacity-40",
                        ext.is_system && "bg-muted/5",
                      )}
                    >
                      <div
                        className={cn(
                          "grid gap-2 items-center px-3 py-1.5",
                          GRID_COLS,
                        )}
                      >
                        {/* Type */}
                        <div className="flex items-center gap-1 min-w-0">
                          {ext.is_system && (
                            <Lock className="h-2.5 w-2.5 text-muted-foreground flex-shrink-0" />
                          )}
                          <span className="text-xs font-mono text-dim truncate">
                            {ext.indicator_type}
                          </span>
                        </div>

                        {/* Source Path */}
                        <code className="text-xs font-mono text-foreground truncate">
                          {ext.source_path}
                        </code>

                        {/* Arrow */}
                        <div className="flex justify-center">
                          <ArrowRight className="h-3 w-3 text-dim flex-shrink-0" />
                        </div>

                        {/* Target Key */}
                        <code className="text-xs font-mono text-teal-light truncate">
                          {ext.target_key}
                        </code>

                        {/* Value Type */}
                        <span className="text-[11px] text-dim truncate">
                          {ext.value_type}
                        </span>

                        {/* Active toggle */}
                        <div className="flex justify-center">
                          <Switch
                            checked={ext.is_active}
                            onCheckedChange={() => handleToggleActive(ext)}
                            className={cn(
                              "scale-75",
                              ext.is_active
                                ? "data-[state=checked]:bg-teal"
                                : "",
                            )}
                          />
                        </div>

                        {/* Edit / Delete */}
                        <div className="flex justify-center">
                          {!ext.is_system ? (
                            <div className="flex gap-0.5">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => startEditing(ext)}
                                className="h-6 w-6 p-0 text-dim hover:text-teal opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Edit"
                              >
                                <Pencil className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setDeleteTarget({
                                    uuid: ext.uuid,
                                    label: `${ext.source_path} → ${ext.target_key}`,
                                  })
                                }
                                className="h-6 w-6 p-0 text-dim hover:text-red-threat opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Delete"
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            </div>
                          ) : (
                            <div className="h-6 w-6" />
                          )}
                        </div>
                      </div>

                      {/* Description subtitle (if present) */}
                      {ext.description && (
                        <div className="px-3 pb-1.5 -mt-0.5">
                          <p className="text-[11px] text-dim pl-[90px] ml-2">
                            {ext.description}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}

            {/* New rows separator */}
            {newRows.length > 0 && grouped.length > 0 && (
              <div className="px-3 py-1.5 bg-teal/5 border-b border-teal/20 flex items-center gap-2">
                <span className="text-xs font-medium text-teal-light">
                  New extractions
                </span>
                <Badge
                  variant="outline"
                  className="text-[10px] text-teal-light border-teal/30"
                >
                  {newRows.length} pending
                </Badge>
              </div>
            )}

            {/* New editable rows */}
            {newRows.map((row, index) => (
              <div
                key={`new-${index}`}
                className="border-b border-teal/20 bg-teal/5 last:border-b-0"
              >
                <div
                  className={cn(
                    "grid gap-2 items-center px-3 py-1.5",
                    GRID_COLS,
                  )}
                >
                  {/* Type select */}
                  <Select
                    value={row.indicator_type}
                    onValueChange={(v) =>
                      updateNewRow(index, "indicator_type", v)
                    }
                  >
                    <SelectTrigger className="h-7 bg-surface border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {supportedIndicatorTypes.map((type) => (
                        <SelectItem key={type} value={type} className="text-xs">
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Source Path */}
                  <Input
                    value={row.source_path}
                    onChange={(e) =>
                      updateNewRow(index, "source_path", e.target.value)
                    }
                    placeholder="data.attributes.reputation"
                    className="h-7 bg-surface border-border text-xs font-mono"
                  />

                  {/* Arrow */}
                  <div className="flex justify-center">
                    <ArrowRight className="h-3 w-3 text-dim flex-shrink-0" />
                  </div>

                  {/* Target Key */}
                  <Input
                    value={row.target_key}
                    onChange={(e) =>
                      updateNewRow(index, "target_key", e.target.value)
                    }
                    placeholder="reputation"
                    className="h-7 bg-surface border-border text-xs font-mono"
                  />

                  {/* Value Type */}
                  <Select
                    value={row.value_type}
                    onValueChange={(v) =>
                      updateNewRow(index, "value_type", v)
                    }
                  >
                    <SelectTrigger className="h-7 bg-surface border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {VALUE_TYPES.map((type) => (
                        <SelectItem key={type} value={type} className="text-xs">
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Save row */}
                  <div className="flex justify-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => saveNewRow(index)}
                      disabled={savingIndex === index}
                      className="h-6 w-6 p-0 text-teal hover:text-teal-light"
                      title="Save this row"
                    >
                      {savingIndex === index ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Check className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>

                  {/* Cancel row */}
                  <div className="flex justify-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeNewRow(index)}
                      className="h-6 w-6 p-0 text-dim hover:text-red-threat"
                      title="Remove this row"
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>

                {/* Description input below — spans from source_path through value_type (col-span-3) */}
                <div
                  className={cn(
                    "grid gap-2 items-center px-3 pb-2 pt-0",
                    GRID_COLS,
                  )}
                >
                  <div />
                  <div className="col-span-3">
                    <Input
                      value={row.description}
                      onChange={(e) =>
                        updateNewRow(index, "description", e.target.value)
                      }
                      placeholder="Description (optional) — e.g. Reputation score from VirusTotal"
                      className="h-6 bg-surface border-border text-[11px] text-dim"
                    />
                  </div>
                  <div />
                  <div />
                  <div />
                </div>
              </div>
            ))}
          </div>

          {/* Hint text
          {newRows.length === 0 && extractions.length > 0 && (
            <p className="text-[11px] text-dim mt-2">
              Click <strong>Add Row</strong> to add a new extraction. Each row
              maps a dot-notation path in the raw API response to a named key in
              the <code className="text-[11px]">extracted</code> object.
            </p>
          )} */}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Field Extraction"
        description={`Delete extraction "${deleteTarget?.label}"? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </>
  );
}
