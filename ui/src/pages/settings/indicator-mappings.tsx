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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { TablePagination } from "@/components/table-pagination";
import { JsonViewer } from "@/components/json-viewer";
import {
  useIndicatorMappings,
  useCreateIndicatorMapping,
  useDeleteIndicatorMapping,
  useSourcePluginFields,
  useTestExtraction,
} from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import type {
  TestExtractionResult,
  TestExtractionPassResult,
  TestExtractionIndicator,
  IndicatorFieldMapping,
} from "@/lib/types";
import {
  Plus,
  Trash2,
  Lock,
  FlaskConical,
  ChevronDown,
  ChevronRight,
  Play,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

const COLUMNS: ColumnDef[] = [
  { key: "source", initialWidth: 120, minWidth: 80 },
  { key: "field_path", initialWidth: 260, minWidth: 120 },
  { key: "indicator_type", initialWidth: 120, minWidth: 80 },
  { key: "system", initialWidth: 70, minWidth: 60 },
  { key: "status", initialWidth: 70, minWidth: 60 },
  { key: "description", initialWidth: 200, minWidth: 100 },
  { key: "created", initialWidth: 140, minWidth: 100 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

import { INDICATOR_TYPES } from "@/lib/types";
const EXTRACTION_TARGETS = [
  { value: "normalized", label: "Normalized" },
  { value: "raw_payload", label: "Raw Payload" },
];
const SOURCE_OPTIONS = ["sentinel", "elastic", "splunk", "generic"];

// --- Test Extraction sub-components ---

function TestIndicatorTable({ indicators }: { indicators: TestExtractionIndicator[] }) {
  if (indicators.length === 0) {
    return <p className="text-xs text-dim italic py-2">No indicators extracted</p>;
  }
  return (
    <div className="rounded border border-border overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-surface">
            <th className="text-left px-2.5 py-1.5 text-dim font-medium">Type</th>
            <th className="text-left px-2.5 py-1.5 text-dim font-medium">Value</th>
            <th className="text-left px-2.5 py-1.5 text-dim font-medium">Source Field</th>
          </tr>
        </thead>
        <tbody>
          {indicators.map((ind, i) => (
            <tr key={`${ind.type}-${ind.value}-${i}`} className="border-b border-border last:border-0">
              <td className="px-2.5 py-1.5">
                <Badge variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
                  {ind.type}
                </Badge>
              </td>
              <td className="px-2.5 py-1.5 font-mono text-foreground">{ind.value}</td>
              <td className="px-2.5 py-1.5 font-mono text-dim">{ind.source_field ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PassResultCard({ pass: p }: { pass: TestExtractionPassResult }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground">{p.pass_label}</span>
        <span className="text-[10px] text-dim">
          {p.error ? "error" : `${p.indicators.length} indicator${p.indicators.length !== 1 ? "s" : ""}`}
        </span>
      </div>
      {p.error ? (
        <div className="flex items-start gap-1.5 text-xs text-red-threat bg-red-threat/10 border border-red-threat/20 rounded px-2.5 py-1.5">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span className="font-mono">{p.error}</span>
        </div>
      ) : (
        <TestIndicatorTable indicators={p.indicators} />
      )}
    </div>
  );
}

function ExtractionResultDisplay({ result }: { result: TestExtractionResult }) {
  const [showPreview, setShowPreview] = useState(false);
  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center gap-3 text-xs">
        {result.success ? (
          <Badge variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
            <CheckCircle2 className="h-3 w-3 mr-1" />success
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[10px] text-red-threat bg-red-threat/10 border-red-threat/20">
            <AlertCircle className="h-3 w-3 mr-1" />failed
          </Badge>
        )}
        <span className="text-dim">{result.duration_ms}ms</span>
        <span className="text-dim">{result.deduplicated_count} unique indicator{result.deduplicated_count !== 1 ? "s" : ""}</span>
      </div>

      <div className="space-y-3">
        {result.passes.map((p) => (
          <PassResultCard key={p.pass_name} pass={p} />
        ))}
      </div>

      {result.normalization_preview && (
        <div>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="flex items-center gap-1 text-xs text-dim hover:text-foreground transition-colors"
          >
            {showPreview ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Normalization Preview
          </button>
          {showPreview && (
            <div className="mt-1.5 rounded border border-border bg-surface p-2 max-h-64 overflow-auto">
              <JsonViewer data={result.normalization_preview} defaultExpanded={1} />
            </div>
          )}
        </div>
      )}

      {result.deduplicated.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-medium text-foreground">Deduplicated Results</span>
          <TestIndicatorTable indicators={result.deduplicated} />
        </div>
      )}
    </div>
  );
}

// --- Source Plugin Fields tab content ---

function SourcePluginFieldsTab({ fields }: { fields: IndicatorFieldMapping[] }) {
  const [filterSource, setFilterSource] = useState<string>("__all__");
  const filtered = filterSource === "__all__"
    ? fields
    : fields.filter((f) => f.source_name === filterSource);

  const sources = [...new Set(fields.map((f) => f.source_name).filter(Boolean))];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-md bg-surface/50 border border-border px-3 h-10">
        <span className="text-xs text-dim">
          Pass 1 — hardcoded in source plugins, read-only
        </span>
        {sources.length > 1 && (
          <Select value={filterSource} onValueChange={setFilterSource}>
            <SelectTrigger className="w-[140px] bg-surface border-border text-xs h-7">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              <SelectItem value="__all__">All sources</SelectItem>
              {sources.map((s) => (
                <SelectItem key={s} value={s!}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-surface">
              <th className="text-left px-3 py-2 text-dim font-medium w-28">Source</th>
              <th className="text-left px-3 py-2 text-dim font-medium">Field Path</th>
              <th className="text-left px-3 py-2 text-dim font-medium w-28">Indicator Type</th>
              <th className="text-left px-3 py-2 text-dim font-medium">Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((f, i) => (
              <tr
                key={`${f.source_name}-${f.field_path}-${f.indicator_type}-${i}`}
                className="border-b border-border last:border-0 hover:bg-accent/30"
              >
                <td className="px-3 py-1.5 font-mono text-foreground">{f.source_name}</td>
                <td className="px-3 py-1.5 font-mono text-foreground">{f.field_path}</td>
                <td className="px-3 py-1.5">
                  <Badge variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
                    {f.indicator_type}
                  </Badge>
                </td>
                <td className="px-3 py-1.5 text-dim">{f.description}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="text-center text-sm text-dim py-8">
                  No source plugin fields{filterSource !== "__all__" ? ` for ${filterSource}` : ""}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-dim">{filtered.length} field{filtered.length !== 1 ? "s" : ""}</p>
    </div>
  );
}

// --- DB Mappings tab content (reused for normalized + raw_payload) ---

function MappingsTab({
  extractionTarget,
  mappings,
  isLoading,
  meta,
  page,
  pageSize,
  setPage,
  handlePageSizeChange,
  onDelete,
  onOpenCreate,
}: {
  extractionTarget: string;
  mappings: IndicatorFieldMapping[];
  isLoading: boolean;
  meta: { total: number; page: number; page_size: number; total_pages: number } | undefined;
  page: number;
  pageSize: number;
  setPage: (p: number) => void;
  handlePageSizeChange: (s: number) => void;
  onDelete: (uuid: string, path: string) => void;
  onOpenCreate: () => void;
}) {
  const filtered = mappings.filter((m) => m.extraction_target === extractionTarget);
  const isNormalized = extractionTarget === "normalized";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-md bg-surface/50 border border-border px-3 h-10">
        <span className="text-xs text-dim">
          {isNormalized
            ? "Pass 2 — match against CalsetaAlert fields, system mappings apply to all sources"
            : "Pass 3 — match against source-specific raw JSON using dot-notation paths"}
        </span>
        <Button size="sm" onClick={onOpenCreate} className="bg-teal text-white hover:bg-teal-dim">
          <Plus className="h-3.5 w-3.5 mr-1" />
          Add Mapping
        </Button>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <ResizableTable storageKey={`indicator-mappings-${extractionTarget}`} columns={COLUMNS}>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <ResizableTableHead columnKey="source" className="text-dim text-xs">Source</ResizableTableHead>
              <ResizableTableHead columnKey="field_path" className="text-dim text-xs">Field Path</ResizableTableHead>
              <ResizableTableHead columnKey="indicator_type" className="text-dim text-xs">Indicator Type</ResizableTableHead>
              <ResizableTableHead columnKey="system" className="text-dim text-xs">System</ResizableTableHead>
              <ResizableTableHead columnKey="status" className="text-dim text-xs">Active</ResizableTableHead>
              <ResizableTableHead columnKey="description" className="text-dim text-xs">Description</ResizableTableHead>
              <ResizableTableHead columnKey="created" className="text-dim text-xs">Created</ResizableTableHead>
              <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i} className="border-border">
                    {Array.from({ length: 8 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                    ))}
                  </TableRow>
                ))
              : filtered.map((m) => (
                  <TableRow
                    key={m.uuid}
                    className={`border-border hover:bg-accent/50 ${m.is_system ? "opacity-70" : ""}`}
                  >
                    <TableCell className="text-xs text-foreground font-mono">
                      {m.source_name || <span className="text-dim italic">all</span>}
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
                    <TableCell className="text-xs text-dim truncate max-w-[200px]">{m.description ?? "—"}</TableCell>
                    <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(m.created_at)}</TableCell>
                    <TableCell>
                      {!m.is_system && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onDelete(m.uuid, m.field_path)}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
            {!isLoading && filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-sm text-dim py-12">
                  No {isNormalized ? "normalized" : "raw payload"} mappings configured
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
  );
}

// --- Main page ---

export function IndicatorMappingsPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } = useTableState({});
  const { data, isLoading } = useIndicatorMappings(params);
  const { data: pluginFieldsData } = useSourcePluginFields();
  const createMapping = useCreateIndicatorMapping();
  const deleteMapping = useDeleteIndicatorMapping();
  const testExtraction = useTestExtraction();
  const [open, setOpen] = useState(false);
  const [createTarget, setCreateTarget] = useState<"normalized" | "raw_payload">("normalized");
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; path: string } | null>(null);

  // Test extraction state
  const [testSource, setTestSource] = useState("sentinel");
  const [rawPayloadText, setRawPayloadText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestExtractionResult | null>(null);

  // Form state
  const [formSource, setFormSource] = useState<string>("__all__");
  const [formType, setFormType] = useState("");

  const mappings = data?.data ?? [];
  const meta = data?.meta;
  const pluginFields = pluginFieldsData?.data ?? [];

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const fieldPath = (fd.get("field_path") as string).trim();
    const description = (fd.get("description") as string)?.trim() || undefined;

    createMapping.mutate(
      {
        source_name: formSource === "__all__" ? null : formSource,
        extraction_target: createTarget,
        field_path: fieldPath,
        indicator_type: formType,
        is_active: true,
        description,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setFormSource("__all__");
          setFormType("");
          toast.success("Indicator mapping created");
        },
        onError: () => toast.error("Failed to create indicator mapping"),
      },
    );
  }

  function handleOpenCreate(target: "normalized" | "raw_payload") {
    setCreateTarget(target);
    setOpen(true);
  }

  function handleRunTest() {
    setJsonError(null);
    if (!rawPayloadText.trim()) {
      setJsonError("Paste a JSON payload first");
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(rawPayloadText);
    } catch {
      setJsonError("Invalid JSON — check syntax");
      return;
    }
    testExtraction.mutate(
      { source_name: testSource, raw_payload: parsed },
      {
        onSuccess: (res) => setTestResult(res.data),
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Test extraction failed";
          toast.error(msg);
        },
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

  const normalizedCount = mappings.filter((m) => m.extraction_target === "normalized").length;
  const rawPayloadCount = mappings.filter((m) => m.extraction_target === "raw_payload").length;

  return (
    <AppLayout title="Indicator Mappings">
      <div className="space-y-4">
        <Tabs defaultValue="source_plugin">
          <TabsList variant="line">
            <TabsTrigger value="source_plugin" className="text-xs gap-1.5">
              Source Plugin
              <Badge variant="outline" className="text-[11px] px-1.5 py-0 text-foreground/60 border-border ml-1">
                {pluginFields.length}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="normalized" className="text-xs gap-1.5">
              Normalized
              <Badge variant="outline" className="text-[11px] px-1.5 py-0 text-foreground/60 border-border ml-1">
                {normalizedCount}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="raw_payload" className="text-xs gap-1.5">
              Raw Payload
              <Badge variant="outline" className="text-[11px] px-1.5 py-0 text-foreground/60 border-border ml-1">
                {rawPayloadCount}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="test" className="text-xs gap-1.5">
              <FlaskConical className="h-3 w-3" />
              Test Extraction
            </TabsTrigger>
          </TabsList>

          <TabsContent value="source_plugin">
            <SourcePluginFieldsTab fields={pluginFields} />
          </TabsContent>

          <TabsContent value="normalized">
            <MappingsTab
              extractionTarget="normalized"
              mappings={mappings}
              isLoading={isLoading}
              meta={meta}
              page={page}
              pageSize={pageSize}
              setPage={setPage}
              handlePageSizeChange={handlePageSizeChange}
              onDelete={(uuid, path) => setDeleteTarget({ uuid, path })}
              onOpenCreate={() => handleOpenCreate("normalized")}
            />
          </TabsContent>

          <TabsContent value="raw_payload">
            <MappingsTab
              extractionTarget="raw_payload"
              mappings={mappings}
              isLoading={isLoading}
              meta={meta}
              page={page}
              pageSize={pageSize}
              setPage={setPage}
              handlePageSizeChange={handlePageSizeChange}
              onDelete={(uuid, path) => setDeleteTarget({ uuid, path })}
              onOpenCreate={() => handleOpenCreate("raw_payload")}
            />
          </TabsContent>

          <TabsContent value="test">
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-md bg-surface/50 border border-border px-3 h-10">
                <span className="text-xs text-dim">
                  Dry-run all 3 extraction passes against a sample payload
                </span>
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1 max-w-[200px]">
                  <Label className="text-xs text-muted-foreground">Source</Label>
                  <Select value={testSource} onValueChange={setTestSource}>
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {SOURCE_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  size="sm"
                  onClick={handleRunTest}
                  disabled={testExtraction.isPending}
                  className="bg-teal text-white hover:bg-teal-dim"
                >
                  {testExtraction.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5 mr-1" />
                  )}
                  Run Test
                </Button>
              </div>
              <textarea
                value={rawPayloadText}
                onChange={(e) => {
                  setRawPayloadText(e.target.value);
                  if (jsonError) setJsonError(null);
                }}
                placeholder='Paste raw alert JSON...'
                className="w-full h-48 rounded border border-border bg-surface text-xs font-mono text-foreground p-2.5 resize-y placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-teal/50"
              />
              {jsonError && (
                <div className="flex items-center gap-1.5 text-xs text-red-threat">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {jsonError}
                </div>
              )}
              {testResult && <ExtractionResultDisplay result={testResult} />}
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Create mapping dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>
              Add {createTarget === "normalized" ? "Normalized" : "Raw Payload"} Mapping
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <div>
              <Label className="text-xs text-muted-foreground">
                {createTarget === "raw_payload"
                  ? "Source (required for raw payload mappings)"
                  : "Source (optional — blank = all sources)"}
              </Label>
              <Select value={formSource} onValueChange={setFormSource}>
                <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                  <SelectValue placeholder="All sources" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {createTarget === "normalized" && (
                    <SelectItem value="__all__">All sources</SelectItem>
                  )}
                  {SOURCE_OPTIONS.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Field Path</Label>
              <Input
                name="field_path"
                required
                className="mt-1 bg-surface border-border text-sm font-mono"
                placeholder={
                  createTarget === "normalized"
                    ? "e.g. src_ip"
                    : "e.g. okta.data.client.ipAddress"
                }
              />
              <p className="text-[11px] text-dim mt-1">
                {createTarget === "normalized"
                  ? "Match against standardized CalsetaAlert field names"
                  : "Dot-notation path into the source raw JSON payload"}
              </p>
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
