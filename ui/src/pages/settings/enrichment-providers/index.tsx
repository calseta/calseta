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
  useEnrichmentProviders,
  useCreateEnrichmentProvider,
  useDeleteEnrichmentProvider,
} from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { SortableColumnHeader } from "@/components/sortable-column-header";
import { ColumnFilterPopover } from "@/components/column-filter-popover";
import { TablePagination } from "@/components/table-pagination";
import { Plus, Trash2, RefreshCw, X, Microscope } from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavigate } from "@tanstack/react-router";

import { INDICATOR_TYPES as ALL_INDICATOR_TYPES } from "@/lib/types";

const EP_COLUMNS: ColumnDef[] = [
  { key: "display_name", initialWidth: 200, minWidth: 140 },
  { key: "provider_name", initialWidth: 150, minWidth: 100 },
  { key: "type", initialWidth: 90, minWidth: 70 },
  { key: "status", initialWidth: 80, minWidth: 70 },
  { key: "configured", initialWidth: 90, minWidth: 70 },
  { key: "indicator_types", initialWidth: 280, minWidth: 160 },
  { key: "created", initialWidth: 160, minWidth: 120 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

const ACTIVE_OPTIONS = [
  { value: "true", label: "Active" },
  { value: "false", label: "Inactive" },
];

const BUILTIN_OPTIONS = [
  { value: "true", label: "Builtin" },
  { value: "false", label: "Custom" },
];

const AUTH_TYPE_OPTIONS = ["no_auth", "api_key", "bearer_token", "basic_auth", "oauth2_client_credentials"];

const SORT_KEY_MAP: Record<string, string> = {
  display_name: "display_name",
  provider_name: "provider_name",
  created: "created_at",
};

export function EnrichmentProvidersPage() {
  const {
    page,
    setPage,
    pageSize,
    handlePageSizeChange,
    sort,
    updateSort,
    filters,
    updateFilter,
    clearAll,
    hasActiveFiltersOrSort,
    hasActiveFilters,
    params,
  } = useTableState({ is_active: [] as string[], is_builtin: [] as string[] });

  const { data, isLoading, refetch, isFetching } = useEnrichmentProviders(params);
  const createProvider = useCreateEnrichmentProvider();
  const deleteProvider = useDeleteEnrichmentProvider();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);
  const [selectedIndicatorTypes, setSelectedIndicatorTypes] = useState<string[]>([]);

  const providers = data?.data ?? [];
  const meta = data?.meta;

  function handleSort(uiKey: string) {
    const apiKey = SORT_KEY_MAP[uiKey] ?? uiKey;
    updateSort(apiKey);
  }

  const reverseSortKeyMap: Record<string, string> = Object.fromEntries(
    Object.entries(SORT_KEY_MAP).map(([ui, api]) => [api, ui]),
  );
  const uiSort = sort
    ? { column: reverseSortKeyMap[sort.column] ?? sort.column, order: sort.order }
    : null;

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);

    if (selectedIndicatorTypes.length === 0) {
      toast.error("Select at least one indicator type");
      return;
    }

    createProvider.mutate(
      {
        provider_name: fd.get("provider_name") as string,
        display_name: fd.get("display_name") as string,
        description: (fd.get("description") as string)?.trim() || undefined,
        supported_indicator_types: selectedIndicatorTypes,
        auth_type: (fd.get("auth_type") as string) || "no_auth",
        http_config: { steps: [] },
        default_cache_ttl_seconds: Number(fd.get("default_cache_ttl_seconds")) || 3600,
      },
      {
        onSuccess: (res) => {
          setOpen(false);
          setSelectedIndicatorTypes([]);
          toast.success("Enrichment provider created");
          const uuid = res?.data?.uuid;
          if (uuid) {
            navigate({ to: "/enrichments/$uuid", params: { uuid } });
          }
        },
        onError: () => toast.error("Failed to create enrichment provider"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteProvider.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Enrichment provider deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete enrichment provider"),
    });
  }

  return (
    <AppLayout title="Enrichment Providers">
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
            {hasActiveFiltersOrSort && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearAll}
                className="h-7 px-2 text-xs text-dim hover:text-foreground gap-1"
              >
                <X className="h-3 w-3" />
                Reset filters
              </Button>
            )}
            {meta && (
              <span className="text-xs text-dim">
                {meta.total} provider{meta.total !== 1 ? "s" : ""}
                {hasActiveFilters && (
                  <span className="text-teal ml-1">(filtered)</span>
                )}
              </span>
            )}
          </div>
          <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setSelectedIndicatorTypes([]); }}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Provider
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Enrichment Provider</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">Provider Name</Label>
                  <Input
                    name="provider_name"
                    required
                    pattern="^[a-z0-9_]+$"
                    placeholder="e.g. my_provider"
                    className="mt-1 bg-surface border-border text-sm font-mono"
                  />
                  <p className="text-[11px] text-dim mt-1">Lowercase letters, numbers, underscores only</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Display Name</Label>
                  <Input name="display_name" required className="mt-1 bg-surface border-border text-sm" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Description</Label>
                  <Textarea name="description" rows={2} className="mt-1 bg-surface border-border text-sm" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Supported Indicator Types</Label>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {ALL_INDICATOR_TYPES.map((type) => {
                      const selected = selectedIndicatorTypes.includes(type);
                      return (
                        <button
                          key={type}
                          type="button"
                          onClick={() =>
                            setSelectedIndicatorTypes((prev) =>
                              selected ? prev.filter((t) => t !== type) : [...prev, type],
                            )
                          }
                          className={cn(
                            "px-2 py-0.5 text-xs rounded border transition-colors",
                            selected
                              ? "border-teal/50 bg-teal/10 text-teal"
                              : "border-border text-dim hover:text-foreground hover:border-foreground/30",
                          )}
                        >
                          {type}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Auth Type</Label>
                  <select
                    name="auth_type"
                    defaultValue="no_auth"
                    className="mt-1 w-full rounded-md bg-surface border border-border text-sm px-3 py-2 text-foreground"
                  >
                    {AUTH_TYPE_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Cache TTL (seconds)</Label>
                  <Input
                    name="default_cache_ttl_seconds"
                    type="number"
                    defaultValue={3600}
                    min={0}
                    max={86400}
                    className="mt-1 bg-surface border-border text-sm"
                  />
                </div>
                <Button type="submit" disabled={createProvider.isPending} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="enrichment-providers" columns={EP_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="display_name" className="micro-label">
                  <SortableColumnHeader
                    label="Display Name"
                    sortKey="display_name"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="provider_name" className="micro-label">
                  <SortableColumnHeader
                    label="Provider"
                    sortKey="provider_name"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="type" className="micro-label">
                  <SortableColumnHeader
                    label="Type"
                    sortKey="type"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Type"
                        options={BUILTIN_OPTIONS}
                        selected={filters.is_builtin}
                        onChange={(v) => updateFilter("is_builtin", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="status" className="micro-label">
                  <SortableColumnHeader
                    label="Status"
                    sortKey="status"
                    currentSort={uiSort}
                    onSort={handleSort}
                    filterElement={
                      <ColumnFilterPopover
                        label="Status"
                        options={ACTIVE_OPTIONS}
                        selected={filters.is_active}
                        onChange={(v) => updateFilter("is_active", v)}
                      />
                    }
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="configured" className="micro-label">Configured</ResizableTableHead>
                <ResizableTableHead columnKey="indicator_types" className="micro-label">Indicator Types</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="micro-label">
                  <SortableColumnHeader
                    label="Created (UTC)"
                    sortKey="created"
                    currentSort={uiSort}
                    onSort={handleSort}
                  />
                </ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="micro-label w-10" />
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
                : providers.map((provider) => (
                    <TableRow key={provider.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          to="/enrichments/$uuid"
                          params={{ uuid: provider.uuid }}
                          className="flex items-center gap-2 hover:text-teal transition-colors"
                        >
                          <Microscope className="h-3.5 w-3.5 text-teal" />
                          <span className="text-sm text-foreground hover:text-teal">{provider.display_name}</span>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-dim font-mono">{provider.provider_name}</span>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[11px]",
                            provider.is_builtin
                              ? "text-muted-foreground bg-muted/50 border-muted"
                              : "text-teal-light bg-teal-light/10 border-teal-light/30",
                          )}
                        >
                          {provider.is_builtin ? "builtin" : "custom"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[11px]",
                            provider.is_active
                              ? "text-teal bg-teal/10 border-teal/30"
                              : "text-dim bg-dim/10 border-dim/30",
                          )}
                        >
                          {provider.is_active ? "active" : "inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className={cn("text-xs", provider.is_configured ? "text-teal" : "text-dim")}>
                          {provider.is_configured ? "yes" : "no"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {provider.supported_indicator_types.length > 0
                            ? provider.supported_indicator_types.map((t) => (
                                <span
                                  key={t}
                                  className="inline-block px-1.5 py-0.5 text-[10px] font-mono text-dim bg-surface-hover rounded border border-border"
                                >
                                  {t}
                                </span>
                              ))
                            : <span className="text-xs text-dim">—</span>
                          }
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">{formatDate(provider.created_at)}</TableCell>
                      <TableCell>
                        {!provider.is_builtin && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTarget({ uuid: provider.uuid, name: provider.display_name })}
                            className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && providers.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-dim py-12">
                    No enrichment providers configured
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
        title="Delete Enrichment Provider"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
