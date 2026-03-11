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
import { TablePagination } from "@/components/table-pagination";
import { useApiKeys, useCreateApiKey, useDeactivateApiKey } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { Plus, Ban, Copy, Check, Key, RefreshCw, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

const ALL_SCOPES = [
  "alerts:read",
  "alerts:write",
  "enrichments:read",
  "workflows:read",
  "workflows:execute",
  "agents:read",
  "agents:write",
  "admin",
];

const ALL_SOURCES = ["sentinel", "elastic", "splunk", "generic"];

const AK_COLUMNS: ColumnDef[] = [
  { key: "prefix", initialWidth: 140, minWidth: 100 },
  { key: "name", initialWidth: 300, minWidth: 160 },
  { key: "scopes", initialWidth: 280, minWidth: 120 },
  { key: "status", initialWidth: 80, minWidth: 70 },
  { key: "last_used", initialWidth: 110, minWidth: 80 },
  { key: "created", initialWidth: 110, minWidth: 80 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

export function ApiKeysPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } = useTableState({});
  const { data, isLoading, refetch, isFetching } = useApiKeys(params);
  const createKey = useCreateApiKey();
  const deactivateKey = useDeactivateApiKey();
  const [open, setOpen] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<{ uuid: string; prefix: string } | null>(null);

  // Create form state
  const [createName, setCreateName] = useState("");
  const [createScopes, setCreateScopes] = useState<string[]>([...ALL_SCOPES]);
  const [createSources, setCreateSources] = useState<string[]>([]);
  const [createExpiry, setCreateExpiry] = useState("");

  const keys = data?.data ?? [];
  const meta = data?.meta;

  function resetCreateForm() {
    setCreateName("");
    setCreateScopes([...ALL_SCOPES]);
    setCreateSources([]);
    setCreateExpiry("");
  }

  function toggleCreateScope(scope: string) {
    setCreateScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  }

  function toggleCreateSource(source: string) {
    setCreateSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source],
    );
  }

  function handleCreate() {
    const body: Record<string, unknown> = {
      name: createName,
      scopes: createScopes,
    };
    if (createSources.length > 0) body.allowed_sources = createSources;
    if (createExpiry) body.expires_at = new Date(createExpiry).toISOString();

    createKey.mutate(body, {
      onSuccess: (resp) => {
        setNewKey((resp as { data: { key: string } }).data.key);
        toast.success("API key created");
      },
      onError: () => toast.error("Failed to create API key"),
    });
  }

  function handleCopy() {
    if (!newKey) return;
    navigator.clipboard.writeText(newKey);
    setCopied(true);
    toast.success("Key copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  }

  function handleRevoke() {
    if (!revokeTarget) return;
    deactivateKey.mutate(revokeTarget.uuid, {
      onSuccess: () => {
        toast.success("API key revoked");
        setRevokeTarget(null);
      },
      onError: () => toast.error("Failed to revoke API key"),
    });
  }

  return (
    <AppLayout title="API Keys">
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
            <span className="text-xs text-dim">{meta?.total ?? keys.length} keys</span>
          </div>
          <Dialog
            open={open}
            onOpenChange={(v) => {
              setOpen(v);
              if (!v) { setNewKey(null); resetCreateForm(); }
            }}
          >
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Create Key
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>
                  {newKey ? "Key Created" : "Create API Key"}
                </DialogTitle>
              </DialogHeader>
              {newKey ? (
                <div className="space-y-3">
                  <p className="text-xs text-amber">
                    Copy this key now — it will not be shown again.
                  </p>
                  <div className="flex gap-2">
                    <Input
                      value={newKey}
                      readOnly
                      className="bg-surface border-border text-sm font-mono"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleCopy}
                      className="shrink-0 border-border"
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-teal" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <Button
                    onClick={() => {
                      setOpen(false);
                      setNewKey(null);
                      resetCreateForm();
                    }}
                    className="w-full bg-teal text-white hover:bg-teal-dim"
                  >
                    Done
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Name */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Name *</Label>
                    <Input
                      value={createName}
                      onChange={(e) => setCreateName(e.target.value)}
                      placeholder="e.g. my-agent, admin-key"
                      className="bg-surface border-border text-sm"
                    />
                  </div>

                  {/* Scopes */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Scopes</Label>
                    <div className="flex flex-wrap gap-2">
                      {ALL_SCOPES.map((scope) => {
                        const selected = createScopes.includes(scope);
                        return (
                          <button
                            key={scope}
                            type="button"
                            onClick={() => toggleCreateScope(scope)}
                            className={cn(
                              "px-2.5 py-1 rounded-md text-xs border transition-colors",
                              selected
                                ? "bg-teal/15 border-teal/40 text-teal-light"
                                : "bg-surface border-border text-dim hover:border-teal/30",
                            )}
                          >
                            {scope}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Allowed Sources */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Allowed Sources</Label>
                    <p className="text-[11px] text-dim">
                      {createSources.length === 0
                        ? "Unrestricted — key can ingest from any source."
                        : `Restricted to ${createSources.length} source(s).`}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {ALL_SOURCES.map((source) => {
                        const selected = createSources.includes(source);
                        return (
                          <button
                            key={source}
                            type="button"
                            onClick={() => toggleCreateSource(source)}
                            className={cn(
                              "px-2.5 py-1 rounded-md text-xs border transition-colors",
                              selected
                                ? "bg-teal/15 border-teal/40 text-teal-light"
                                : "bg-surface border-border text-dim hover:border-teal/30",
                            )}
                          >
                            {source}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Expiration */}
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">
                      <Calendar className="h-3.5 w-3.5 inline mr-1" />
                      Expiration
                    </Label>
                    <Input
                      type="datetime-local"
                      value={createExpiry}
                      onChange={(e) => setCreateExpiry(e.target.value)}
                      className="bg-surface border-border text-sm"
                    />
                    <p className="text-[11px] text-dim">
                      Leave empty for a non-expiring key.
                    </p>
                  </div>

                  <Button
                    onClick={handleCreate}
                    disabled={createKey.isPending || !createName.trim() || createScopes.length === 0}
                    className="w-full bg-teal text-white hover:bg-teal-dim"
                  >
                    Create
                  </Button>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="api-keys" columns={AK_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="prefix" className="text-dim text-xs">Prefix</ResizableTableHead>
                <ResizableTableHead columnKey="name" className="text-dim text-xs">Name</ResizableTableHead>
                <ResizableTableHead columnKey="scopes" className="text-dim text-xs">Scopes</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Status</ResizableTableHead>
                <ResizableTableHead columnKey="last_used" className="text-dim text-xs">Last Used</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">Created</ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-5 w-16" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : keys.map((k) => (
                    <TableRow
                      key={k.uuid}
                      className="border-border hover:bg-accent/50"
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Key className="h-3.5 w-3.5 text-teal" />
                          <span className="text-sm font-mono text-foreground">
                            {k.key_prefix}...
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Link
                          to={`/settings/api-keys/${k.uuid}`}
                          className="text-sm text-teal-light hover:underline"
                        >
                          {k.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1 max-w-64">
                          {k.scopes.map((scope) => (
                            <code key={scope} className="text-[10px] font-mono text-dim bg-surface px-1.5 py-0.5 rounded border border-border">
                              {scope}
                            </code>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            k.is_active
                              ? "text-teal bg-teal/10 border-teal/30 text-[11px]"
                              : "text-dim bg-dim/10 border-dim/30 text-[11px]"
                          }
                        >
                          {k.is_active ? "active" : "revoked"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {k.last_used_at
                          ? formatDate(k.last_used_at)
                          : "never"}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {formatDate(k.created_at)}
                      </TableCell>
                      <TableCell>
                        {k.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setRevokeTarget({ uuid: k.uuid, prefix: k.key_prefix })}
                            className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                          >
                            <Ban className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && keys.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No API keys created
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
        open={!!revokeTarget}
        onOpenChange={(v) => !v && setRevokeTarget(null)}
        title="Revoke API Key"
        description={`Are you sure you want to revoke the API key "${revokeTarget?.prefix}..."? This action cannot be undone. Any clients using this key will lose access immediately.`}
        confirmLabel="Revoke"
        onConfirm={handleRevoke}
      />
    </AppLayout>
  );
}
