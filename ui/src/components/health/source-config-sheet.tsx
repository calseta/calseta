import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Cloud,
  Plus,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/format";
import type { HealthSource } from "@/lib/types";
import {
  useHealthSources,
  useCreateHealthSource,
  usePatchHealthSource,
  useDeleteHealthSource,
  useTestHealthSource,
} from "@/hooks/use-api";

interface SourceConfigSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ViewMode = "list" | "add" | "edit";

export function SourceConfigSheet({ open, onOpenChange }: SourceConfigSheetProps) {
  const [view, setView] = useState<ViewMode>("list");
  const [editingSource, setEditingSource] = useState<HealthSource | null>(null);

  const handleClose = (value: boolean) => {
    if (!value) {
      setView("list");
      setEditingSource(null);
    }
    onOpenChange(value);
  };

  return (
    <Sheet open={open} onOpenChange={handleClose}>
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] overflow-y-auto p-6">
        {view === "list" && (
          <SourceList
            onAdd={() => setView("add")}
            onEdit={(s) => { setEditingSource(s); setView("edit"); }}
          />
        )}
        {view === "add" && (
          <SourceForm
            onBack={() => setView("list")}
            onSaved={() => setView("list")}
          />
        )}
        {view === "edit" && editingSource && (
          <SourceForm
            source={editingSource}
            onBack={() => { setView("list"); setEditingSource(null); }}
            onSaved={() => { setView("list"); setEditingSource(null); }}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Source List
// ---------------------------------------------------------------------------

function SourceList({ onAdd, onEdit }: { onAdd: () => void; onEdit: (s: HealthSource) => void }) {
  const { data } = useHealthSources();
  const deleteSource = useDeleteHealthSource();
  const testSource = useTestHealthSource();
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const sources = data?.data ?? [];

  const handleTest = async (uuid: string) => {
    setTesting(uuid);
    try {
      const result = await testSource.mutateAsync(uuid);
      setTestResults((prev) => ({ ...prev, [uuid]: result.data }));
    } catch {
      setTestResults((prev) => ({ ...prev, [uuid]: { success: false, message: "Connection test failed" } }));
    } finally {
      setTesting(null);
    }
  };

  const handleDelete = async (uuid: string) => {
    if (!confirm("Delete this health source and all its metrics?")) return;
    setDeleting(uuid);
    try {
      await deleteSource.mutateAsync(uuid);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <>
      <SheetHeader>
        <SheetTitle>Health Sources</SheetTitle>
        <SheetDescription>
          Configure cloud provider connections for infrastructure monitoring.
        </SheetDescription>
      </SheetHeader>

      <div className="mt-4 space-y-3">
        <Button size="sm" onClick={onAdd} className="w-full gap-1.5">
          <Plus className="h-3.5 w-3.5" />
          Source
        </Button>

        {sources.length === 0 ? (
          <div className="py-8 text-center text-sm text-dim">
            No health sources configured yet.
          </div>
        ) : (
          <div className="space-y-2">
            {sources.map((source) => {
              const testResult = testResults[source.uuid];
              return (
                <div
                  key={source.uuid}
                  className="rounded-lg border border-border p-3 space-y-2"
                >
                  <div className="flex items-center gap-2">
                    <Cloud className="h-4 w-4 text-dim shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{source.name}</p>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {source.provider.toUpperCase()}
                        </Badge>
                        <span className="text-[10px] text-dim">
                          {source.metric_count} metric{source.metric_count !== 1 ? "s" : ""}
                        </span>
                        {source.last_poll_at && (
                          <span className="text-[10px] text-dim">
                            polled {relativeTime(source.last_poll_at)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className={cn("h-2 w-2 rounded-full shrink-0", source.is_active ? "bg-teal" : "bg-dim")} />
                  </div>

                  {source.last_poll_error && (
                    <p className="text-[10px] text-red-threat truncate">{source.last_poll_error}</p>
                  )}

                  {testResult && (
                    <div className={cn("flex items-center gap-1.5 text-[10px]", testResult.success ? "text-teal" : "text-red-threat")}>
                      {testResult.success ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                      {testResult.message}
                    </div>
                  )}

                  <div className="flex gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs px-2"
                      onClick={() => onEdit(source)}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs px-2"
                      onClick={() => handleTest(source.uuid)}
                      disabled={testing === source.uuid}
                    >
                      {testing === source.uuid ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs px-2 text-red-threat hover:text-red-threat"
                      onClick={() => handleDelete(source.uuid)}
                      disabled={deleting === source.uuid}
                    >
                      {deleting === source.uuid ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Source Form (create or edit)
// ---------------------------------------------------------------------------

function SourceForm({
  source,
  onBack,
  onSaved,
}: {
  source?: HealthSource;
  onBack: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!source;
  const createSource = useCreateHealthSource();
  const patchSource = usePatchHealthSource();

  const [name, setName] = useState(source?.name ?? "");
  const [provider, setProvider] = useState(source?.provider ?? "aws");
  const [region, setRegion] = useState((source?.config?.region as string) ?? "");
  const [isActive, setIsActive] = useState(source?.is_active ?? true);
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [tenantId, setTenantId] = useState((source?.config?.tenant_id as string) ?? "");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [subscriptionId, setSubscriptionId] = useState((source?.config?.subscription_id as string) ?? "");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const config: Record<string, unknown> = {};
      const authConfig: Record<string, unknown> = {};

      if (provider === "aws") {
        if (region) config.region = region;
        if (accessKeyId) authConfig.aws_access_key_id = accessKeyId;
        if (secretAccessKey) authConfig.aws_secret_access_key = secretAccessKey;
      } else {
        if (tenantId) config.tenant_id = tenantId;
        if (subscriptionId) config.subscription_id = subscriptionId;
        if (clientId) authConfig.client_id = clientId;
        if (clientSecret) authConfig.client_secret = clientSecret;
      }

      if (isEdit) {
        await patchSource.mutateAsync({
          uuid: source!.uuid,
          body: {
            name,
            config: Object.keys(config).length > 0 ? config : undefined,
            auth_config: Object.keys(authConfig).length > 0 ? authConfig : undefined,
            is_active: isActive,
          },
        });
      } else {
        await createSource.mutateAsync({
          name,
          provider,
          config,
          auth_config: Object.keys(authConfig).length > 0 ? authConfig : undefined,
          is_active: isActive,
        });
      }
      onSaved();
    } catch {
      // Error handled by react-query
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SheetHeader>
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="text-dim hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <SheetTitle>{isEdit ? "Edit Source" : "Add Health Source"}</SheetTitle>
        </div>
        <SheetDescription>
          {isEdit
            ? "Update the configuration for this health source."
            : "Connect a cloud provider to monitor infrastructure health."}
        </SheetDescription>
      </SheetHeader>

      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Production AWS" required />
        </div>

        <div className="space-y-2">
          <Label>Provider</Label>
          <Select value={provider} onValueChange={setProvider} disabled={isEdit}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="aws">AWS CloudWatch</SelectItem>
              <SelectItem value="azure">Azure Monitor</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {provider === "aws" ? (
          <>
            <div className="space-y-2">
              <Label htmlFor="region">Region</Label>
              <Input id="region" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="accessKeyId">Access Key ID</Label>
              <Input id="accessKeyId" value={accessKeyId} onChange={(e) => setAccessKeyId(e.target.value)} placeholder={isEdit ? "(unchanged)" : ""} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="secretAccessKey">Secret Access Key</Label>
              <Input id="secretAccessKey" type="password" value={secretAccessKey} onChange={(e) => setSecretAccessKey(e.target.value)} placeholder={isEdit ? "(unchanged)" : ""} />
            </div>
          </>
        ) : (
          <>
            <div className="space-y-2">
              <Label htmlFor="tenantId">Tenant ID</Label>
              <Input id="tenantId" value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="subscriptionId">Subscription ID</Label>
              <Input id="subscriptionId" value={subscriptionId} onChange={(e) => setSubscriptionId(e.target.value)} placeholder="" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="clientId">Client ID</Label>
              <Input id="clientId" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder={isEdit ? "(unchanged)" : ""} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="clientSecret">Client Secret</Label>
              <Input id="clientSecret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder={isEdit ? "(unchanged)" : ""} />
            </div>
          </>
        )}

        <div className="flex items-center gap-2">
          <Switch id="active" checked={isActive} onCheckedChange={setIsActive} />
          <Label htmlFor="active">Active</Label>
        </div>

        <Button type="submit" className="w-full" disabled={saving || !name}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          {isEdit ? "Update Source" : "Create Source"}
        </Button>
      </form>
    </>
  );
}
