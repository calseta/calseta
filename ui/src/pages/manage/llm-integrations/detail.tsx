import { useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useLLMIntegration,
  useLLMIntegrationUsage,
  usePatchLLMIntegration,
  useTestLLMIntegration,
  useDeleteLLMIntegration,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  DetailPageHeader,
} from "@/components/detail-page";
import { MoreHorizontal, Pencil, BarChart3, Settings, Wifi, Loader2, Trash2 } from "lucide-react";

const PROVIDER_DISPLAY: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  azure_openai: "Azure OpenAI",
  claude_code: "Claude Code",
  aws_bedrock: "AWS Bedrock",
  ollama: "Ollama",
};

function providerBadgeClass(p: string): string {
  switch (p) {
    case "anthropic":
      return "text-amber bg-amber/10 border-amber/30";
    case "openai":
      return "text-teal bg-teal/10 border-teal/30";
    case "azure_openai":
      return "text-blue-400 bg-blue-400/10 border-blue-400/30";
    case "claude_code":
      return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "aws_bedrock":
      return "text-amber bg-amber/10 border-amber/30";
    case "ollama":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function formatCostDollars(cents: number): string {
  return `$${(cents / 100).toFixed(4)}`;
}

// base_url requirement per provider (mirrors create form)
const BASE_URL_REQUIRED = new Set(["azure_openai", "ollama"]);
const BASE_URL_OPTIONAL = new Set(["openai"]);

function baseUrlBehavior(p: string): "required" | "optional" | "none" {
  if (BASE_URL_REQUIRED.has(p)) return "required";
  if (BASE_URL_OPTIONAL.has(p)) return "optional";
  return "none";
}

const BASE_URL_PLACEHOLDER: Record<string, string> = {
  azure_openai: "https://{resource}.openai.azure.com/",
  ollama: "http://localhost:11434",
  openai: "https://api.openai.com/v1",
};

interface EditFormState {
  name: string;
  model: string;
  api_key_ref: string;
  base_url: string;
  is_default: boolean;
}

export function LLMIntegrationDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const navigate = useNavigate();
  const { data, isLoading, refetch, isFetching } = useLLMIntegration(uuid);
  const { data: usageData, isLoading: usageLoading } = useLLMIntegrationUsage(uuid);
  const patchIntegration = usePatchLLMIntegration();
  const testIntegration = useTestLLMIntegration();
  const deleteIntegration = useDeleteLLMIntegration();

  const [showEditDialog, setShowEditDialog] = useState(false);
  const [draft, setDraft] = useState<EditFormState | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const integration = data?.data;
  const usage = usageData?.data;

  function openEditDialog() {
    if (!integration) return;
    setDraft({
      name: integration.name,
      model: integration.model,
      api_key_ref: "",
      base_url: integration.base_url ?? "",
      is_default: integration.is_default,
    });
    setShowEditDialog(true);
  }

  function closeEditDialog() {
    setDraft(null);
    setShowEditDialog(false);
  }

  function handleSave() {
    if (!draft || !integration) return;

    if (
      baseUrlBehavior(integration.provider) === "required" &&
      !draft.base_url.trim()
    ) {
      toast.error(`Base URL is required for ${PROVIDER_DISPLAY[integration.provider] ?? integration.provider}`);
      return;
    }

    const body: Record<string, unknown> = {};

    if (draft.name.trim() !== integration.name) body.name = draft.name.trim();
    if (draft.model.trim() !== integration.model) body.model = draft.model.trim();
    if (draft.is_default !== integration.is_default) body.is_default = draft.is_default;
    if (draft.api_key_ref.trim()) body.api_key_ref = draft.api_key_ref.trim();
    if (draft.base_url.trim() !== (integration.base_url ?? "")) {
      body.base_url = draft.base_url.trim() || null;
    }

    if (Object.keys(body).length === 0) {
      closeEditDialog();
      return;
    }

    patchIntegration.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Integration updated");
          closeEditDialog();
        },
        onError: () => toast.error("Failed to update integration"),
      },
    );
  }

  if (isLoading) {
    return (
      <AppLayout title="LLM Integration">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!integration) {
    return (
      <AppLayout title="LLM Integration">
        <div className="text-center text-dim py-20">Integration not found</div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title={integration.name}>
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/llm-integrations"
          title={integration.name}
          badges={
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn("text-xs", providerBadgeClass(integration.provider))}
              >
                {PROVIDER_DISPLAY[integration.provider] ?? integration.provider}
              </Badge>
              {integration.is_default && (
                <Badge
                  variant="outline"
                  className="text-xs text-teal bg-teal/10 border-teal/30"
                >
                  default
                </Badge>
              )}
            </div>
          }
          onRefresh={refetch}
          isRefreshing={isFetching}
          actions={
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                disabled={testIntegration.isPending}
                onClick={() => {
                  testIntegration.mutate(uuid, {
                    onSuccess: (res) => {
                      const r = res as unknown as { success: boolean; latency_ms: number; message: string };
                      if (r.success) {
                        toast.success(`Connected — ${r.latency_ms}ms`);
                      } else {
                        toast.error(r.message || "Connection failed");
                      }
                    },
                    onError: () => toast.error("Connection test failed"),
                  });
                }}
              >
                {testIntegration.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Wifi className="h-3.5 w-3.5" />
                )}
                Test
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={openEditDialog}
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-dim hover:text-foreground">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-card border-border">
                  <DropdownMenuItem
                    onClick={() => setShowDeleteConfirm(true)}
                    className="text-red-threat focus:text-red-threat focus:bg-red-threat/10 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          }
        />

        <Tabs defaultValue="configuration">
          <TabsList className="bg-surface border border-border">
            <TabsTrigger
              value="configuration"
              className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm"
            >
              <Settings className="h-3.5 w-3.5 mr-1.5" />
              Configuration
            </TabsTrigger>
            <TabsTrigger
              value="usage"
              className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm"
            >
              <BarChart3 className="h-3.5 w-3.5 mr-1.5" />
              Usage
            </TabsTrigger>
          </TabsList>

          {/* Configuration Tab */}
          <TabsContent value="configuration" className="pt-6">
            <Card className="border-border bg-card">
              <CardHeader className="pb-4">
                <CardTitle className="text-sm font-semibold text-foreground">
                  Integration Settings
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Name */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Name</Label>
                  <p className="text-sm text-foreground">{integration.name}</p>
                </div>

                {/* Provider (read-only) */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Provider</Label>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={cn("text-xs", providerBadgeClass(integration.provider))}
                    >
                      {PROVIDER_DISPLAY[integration.provider] ?? integration.provider}
                    </Badge>
                    <span className="text-xs text-dim">(cannot be changed)</span>
                  </div>
                </div>

                {/* Model */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Model</Label>
                  <p className="text-sm text-foreground font-mono">{integration.model}</p>
                </div>

                {/* API Key */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">API Key Env Var</Label>
                  <div className="flex items-center gap-2">
                    {integration.api_key_ref_set ? (
                      <Badge
                        variant="outline"
                        className="text-xs text-teal bg-teal/10 border-teal/30"
                      >
                        configured
                      </Badge>
                    ) : (
                      <span className="text-xs text-dim">Not set</span>
                    )}
                  </div>
                </div>

                {/* Base URL — shown when provider uses it */}
                {baseUrlBehavior(integration.provider) !== "none" && (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-dim uppercase tracking-wide">
                      Base URL
                      {baseUrlBehavior(integration.provider) === "optional" && (
                        <span className="font-normal normal-case ml-1 text-dim">(optional)</span>
                      )}
                    </Label>
                    <p className="text-sm text-foreground font-mono">
                      {integration.base_url ?? <span className="text-dim">Not set</span>}
                    </p>
                  </div>
                )}

                {/* Default */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Default Integration</Label>
                  <p className="text-sm text-foreground">
                    {integration.is_default ? "Yes" : "No"}
                  </p>
                </div>

                {/* Costs (read-only) */}
                <div className="grid grid-cols-2 gap-6 pt-2 border-t border-border">
                  <div className="space-y-1">
                    <Label className="text-xs text-dim uppercase tracking-wide">
                      Input cost / 1k tokens
                    </Label>
                    <p className="text-sm text-foreground">
                      {integration.cost_per_1k_input_tokens_cents}¢
                    </p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-dim uppercase tracking-wide">
                      Output cost / 1k tokens
                    </Label>
                    <p className="text-sm text-foreground">
                      {integration.cost_per_1k_output_tokens_cents}¢
                    </p>
                  </div>
                </div>

                {/* Timestamps */}
                <div className="grid grid-cols-2 gap-6 pt-2 border-t border-border">
                  <div className="space-y-1">
                    <Label className="text-xs text-dim uppercase tracking-wide">Created</Label>
                    <p className="text-xs text-dim">{formatDate(integration.created_at)}</p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-dim uppercase tracking-wide">Updated</Label>
                    <p className="text-xs text-dim">{formatDate(integration.updated_at)}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Usage Tab */}
          <TabsContent value="usage" className="pt-6">
            {usageLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            ) : !usage ? (
              <div className="text-center text-sm text-dim py-20">
                No usage data available
              </div>
            ) : (
              <div className="space-y-4">
                {/* Period */}
                <p className="text-xs text-dim">
                  Period: {formatDate(usage.from_dt)} — {formatDate(usage.to_dt)}
                </p>

                {/* Summary cards */}
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Card className="border-border bg-card">
                    <CardContent className="pt-4 pb-4">
                      <p className="text-xs text-dim uppercase tracking-wide mb-1">Total Cost</p>
                      <p className="text-xl font-bold text-foreground">
                        {formatCostDollars(usage.total_cost_cents)}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="border-border bg-card">
                    <CardContent className="pt-4 pb-4">
                      <p className="text-xs text-dim uppercase tracking-wide mb-1">Events</p>
                      <p className="text-xl font-bold text-foreground">
                        {usage.event_count.toLocaleString()}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="border-border bg-card">
                    <CardContent className="pt-4 pb-4">
                      <p className="text-xs text-dim uppercase tracking-wide mb-1">Input Tokens</p>
                      <p className="text-xl font-bold text-foreground">
                        {usage.total_input_tokens.toLocaleString()}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="border-border bg-card">
                    <CardContent className="pt-4 pb-4">
                      <p className="text-xs text-dim uppercase tracking-wide mb-1">Output Tokens</p>
                      <p className="text-xl font-bold text-foreground">
                        {usage.total_output_tokens.toLocaleString()}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {/* Billing type breakdown */}
                {Object.keys(usage.billing_types).length > 0 && (
                  <Card className="border-border bg-card">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Billing Type Breakdown</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {Object.entries(usage.billing_types).map(([type, count]) => (
                          <div key={type} className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground capitalize">{type}</span>
                            <span className="text-sm font-medium text-foreground">
                              {(count as number).toLocaleString()} events
                            </span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Edit Dialog */}
      {draft && (
        <Dialog open={showEditDialog} onOpenChange={(v) => !v && closeEditDialog()}>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{integration.name}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              {/* Name */}
              <div className="space-y-1.5">
                <Label>Name</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft((d) => d ? { ...d, name: e.target.value } : d)}
                  autoFocus
                />
              </div>

              {/* Provider (read-only) */}
              <div className="space-y-1.5">
                <Label>Provider</Label>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={cn("text-xs", providerBadgeClass(integration.provider))}
                  >
                    {PROVIDER_DISPLAY[integration.provider] ?? integration.provider}
                  </Badge>
                  <span className="text-xs text-dim">(cannot be changed)</span>
                </div>
              </div>

              {/* Model */}
              <div className="space-y-1.5">
                <Label>Model</Label>
                <Input
                  value={draft.model}
                  onChange={(e) => setDraft((d) => d ? { ...d, model: e.target.value } : d)}
                  className="font-mono"
                />
              </div>

              {/* API Key Ref */}
              <div className="space-y-1.5">
                <Label>API Key Env Var</Label>
                <Input
                  value={draft.api_key_ref}
                  onChange={(e) => setDraft((d) => d ? { ...d, api_key_ref: e.target.value } : d)}
                  placeholder="e.g. ANTHROPIC_API_KEY (leave blank to keep current)"
                />
                <p className="text-xs text-dim">Leave blank to keep the existing key reference.</p>
              </div>

              {/* Base URL */}
              {baseUrlBehavior(integration.provider) !== "none" && (
                <div className="space-y-1.5">
                  <Label>
                    Base URL
                    {baseUrlBehavior(integration.provider) === "optional" && (
                      <span className="font-normal ml-1 text-dim">(optional)</span>
                    )}
                  </Label>
                  <Input
                    value={draft.base_url}
                    onChange={(e) => setDraft((d) => d ? { ...d, base_url: e.target.value } : d)}
                    placeholder={BASE_URL_PLACEHOLDER[integration.provider] ?? "https://"}
                    className="font-mono"
                    required={baseUrlBehavior(integration.provider) === "required"}
                  />
                </div>
              )}

              {/* Default */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="edit-is-default"
                  className="rounded border-border"
                  checked={draft.is_default}
                  onChange={(e) =>
                    setDraft((d) => d ? { ...d, is_default: e.target.checked } : d)
                  }
                />
                <Label htmlFor="edit-is-default" className="cursor-pointer font-normal">
                  Use as default LLM integration
                </Label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={closeEditDialog} disabled={patchIntegration.isPending}>
                Cancel
              </Button>
              <Button
                className="bg-teal text-white hover:bg-teal-dim"
                onClick={handleSave}
                disabled={patchIntegration.isPending}
              >
                {patchIntegration.isPending ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete LLM Integration"
        description={`Are you sure you want to delete "${integration.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => {
          deleteIntegration.mutate(uuid, {
            onSuccess: () => {
              toast.success("Integration deleted");
              navigate({ to: "/llm-integrations" });
            },
            onError: () => toast.error("Failed to delete integration"),
          });
        }}
      />
    </AppLayout>
  );
}
