import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
} from "@/components/detail-page";
import { useApiKey, usePatchApiKey, useDeactivateApiKey } from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Key,
  Shield,
  Clock,
  Calendar,
  Ban,
  Save,
  Loader2,
} from "lucide-react";

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

export function ApiKeyDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data, isLoading } = useApiKey(uuid);
  const patchApiKey = usePatchApiKey();
  const deactivateKey = useDeactivateApiKey();

  const [scopesDraft, setScopesDraft] = useState<string[] | null>(null);
  const [sourcesDraft, setSourcesDraft] = useState<string[] | null | "unrestricted">(null);
  const [revokeOpen, setRevokeOpen] = useState(false);

  const apiKey = data?.data;

  if (isLoading) {
    return (
      <AppLayout title="API Key">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!apiKey) {
    return (
      <AppLayout title="API Key">
        <div className="text-center text-dim py-20">API key not found</div>
      </AppLayout>
    );
  }

  const effectiveScopes = scopesDraft ?? apiKey.scopes;
  const effectiveSources =
    sourcesDraft === "unrestricted"
      ? null
      : sourcesDraft !== null
        ? sourcesDraft
        : apiKey.allowed_sources;

  const scopesDirty = scopesDraft !== null;
  const sourcesDirty = sourcesDraft !== null;

  function toggleScope(scope: string) {
    const current = scopesDraft ?? [...apiKey!.scopes];
    const next = current.includes(scope)
      ? current.filter((s) => s !== scope)
      : [...current, scope];
    setScopesDraft(next);
  }

  function toggleSource(source: string) {
    const current =
      sourcesDraft === "unrestricted" || sourcesDraft === null
        ? [...(apiKey!.allowed_sources ?? [])]
        : [...sourcesDraft];
    const next = current.includes(source)
      ? current.filter((s) => s !== source)
      : [...current, source];
    setSourcesDraft(next.length === 0 ? "unrestricted" : next);
  }

  function handleSaveScopes() {
    if (!scopesDraft) return;
    patchApiKey.mutate(
      { uuid, body: { scopes: scopesDraft } },
      {
        onSuccess: () => {
          toast.success("Scopes updated");
          setScopesDraft(null);
        },
        onError: () => toast.error("Failed to update scopes"),
      },
    );
  }

  function handleSaveSources() {
    if (sourcesDraft === null) return;
    const value = sourcesDraft === "unrestricted" ? null : sourcesDraft;
    patchApiKey.mutate(
      { uuid, body: { allowed_sources: value } },
      {
        onSuccess: () => {
          toast.success("Allowed sources updated");
          setSourcesDraft(null);
        },
        onError: () => toast.error("Failed to update allowed sources"),
      },
    );
  }

  function handleRevoke() {
    deactivateKey.mutate(uuid, {
      onSuccess: () => {
        toast.success("API key revoked");
        setRevokeOpen(false);
      },
      onError: () => toast.error("Failed to revoke API key"),
    });
  }

  return (
    <AppLayout title="API Key Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/settings/api-keys"
          title={apiKey.name}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  apiKey.is_active
                    ? "text-teal bg-teal/10 border-teal/30"
                    : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {apiKey.is_active ? "active" : "revoked"}
              </Badge>
              <span className="text-xs font-mono text-dim">{apiKey.key_prefix}...</span>
            </>
          }
          actions={
            apiKey.is_active ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setRevokeOpen(true)}
                className="border-red-threat/30 text-red-threat hover:bg-red-threat/10 text-xs"
              >
                <Ban className="h-3 w-3 mr-1" />
                Revoke
              </Button>
            ) : undefined
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "Status",
              icon: Shield,
              value: (
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    apiKey.is_active
                      ? "text-teal bg-teal/10 border-teal/30"
                      : "text-dim bg-dim/10 border-dim/30",
                  )}
                >
                  {apiKey.is_active ? "active" : "revoked"}
                </Badge>
              ),
            },
            {
              label: "Expires",
              icon: Calendar,
              value: apiKey.expires_at ? formatDate(apiKey.expires_at) : "Never",
            },
            {
              label: "Last Used",
              icon: Clock,
              value: apiKey.last_used_at ? relativeTime(apiKey.last_used_at) : "Never",
            },
          ]}
        />

        <DetailPageLayout
          sidebar={
            <DetailPageSidebar>
              <SidebarSection title="Details">
                <DetailPageField label="UUID" value={apiKey.uuid.slice(0, 8) + "..."} mono />
                <DetailPageField label="Key Prefix" value={apiKey.key_prefix + "..."} mono />
                <DetailPageField label="Name" value={apiKey.name} />
                <DetailPageField label="Created" value={formatDate(apiKey.created_at)} />
                <DetailPageField
                  label="Last Used"
                  value={apiKey.last_used_at ? relativeTime(apiKey.last_used_at) : "Never"}
                />
                <DetailPageField
                  label="Expires"
                  value={apiKey.expires_at ? formatDate(apiKey.expires_at) : "Never"}
                />
              </SidebarSection>
            </DetailPageSidebar>
          }
        >
          <div className="space-y-6">
            {/* Scopes */}
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-foreground">Scopes</CardTitle>
                {scopesDirty && (
                  <Button
                    size="sm"
                    onClick={handleSaveScopes}
                    disabled={patchApiKey.isPending}
                    className="bg-teal text-white hover:bg-teal-dim text-xs"
                  >
                    {patchApiKey.isPending ? (
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    ) : (
                      <Save className="h-3 w-3 mr-1" />
                    )}
                    Save
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {ALL_SCOPES.map((scope) => {
                    const selected = effectiveScopes.includes(scope);
                    return (
                      <button
                        key={scope}
                        type="button"
                        disabled={!apiKey.is_active}
                        onClick={() => toggleScope(scope)}
                        className={cn(
                          "px-3 py-1.5 rounded-md text-xs border transition-colors",
                          selected
                            ? "bg-teal/15 border-teal/40 text-teal-light"
                            : "bg-surface border-border text-dim hover:border-teal/30",
                          !apiKey.is_active && "opacity-50 cursor-not-allowed",
                        )}
                      >
                        {scope}
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Allowed Sources */}
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-foreground">Allowed Sources</CardTitle>
                {sourcesDirty && (
                  <Button
                    size="sm"
                    onClick={handleSaveSources}
                    disabled={patchApiKey.isPending}
                    className="bg-teal text-white hover:bg-teal-dim text-xs"
                  >
                    {patchApiKey.isPending ? (
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    ) : (
                      <Save className="h-3 w-3 mr-1" />
                    )}
                    Save
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                <p className="text-xs text-dim mb-3">
                  {effectiveSources === null
                    ? "Unrestricted — this key can ingest from any source."
                    : `Restricted to ${effectiveSources.length} source(s).`}
                </p>
                <div className="flex flex-wrap gap-2">
                  {ALL_SOURCES.map((source) => {
                    const selected = effectiveSources?.includes(source) ?? false;
                    return (
                      <button
                        key={source}
                        type="button"
                        disabled={!apiKey.is_active}
                        onClick={() => toggleSource(source)}
                        className={cn(
                          "px-3 py-1.5 rounded-md text-xs border transition-colors",
                          selected
                            ? "bg-teal/15 border-teal/40 text-teal-light"
                            : "bg-surface border-border text-dim hover:border-teal/30",
                          !apiKey.is_active && "opacity-50 cursor-not-allowed",
                        )}
                      >
                        {source}
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>
        </DetailPageLayout>
      </div>

      <ConfirmDialog
        open={revokeOpen}
        onOpenChange={setRevokeOpen}
        title="Revoke API Key"
        description={`Are you sure you want to revoke the API key "${apiKey.key_prefix}..."? This action cannot be undone. Any clients using this key will lose access immediately.`}
        confirmLabel="Revoke"
        onConfirm={handleRevoke}
      />
    </AppLayout>
  );
}
