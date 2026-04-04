import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useLLMIntegration,
  useLLMIntegrationUsage,
  usePatchLLMIntegration,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  DetailPageHeader,
} from "@/components/detail-page";
import { Pencil, Save, X, BarChart3, Settings } from "lucide-react";

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

interface EditFormState {
  name: string;
  model: string;
  api_key_ref: string;
  is_default: boolean;
}

export function LLMIntegrationDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data, isLoading, refetch, isFetching } = useLLMIntegration(uuid);
  const { data: usageData, isLoading: usageLoading } = useLLMIntegrationUsage(uuid);
  const patchIntegration = usePatchLLMIntegration();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EditFormState | null>(null);

  const integration = data?.data;
  const usage = usageData?.data;

  function startEditing() {
    if (!integration) return;
    setDraft({
      name: integration.name,
      model: integration.model,
      api_key_ref: "",
      is_default: integration.is_default,
    });
    setEditing(true);
  }

  function cancelEditing() {
    setDraft(null);
    setEditing(false);
  }

  function handleSave() {
    if (!draft || !integration) return;
    const body: Record<string, unknown> = {};

    if (draft.name.trim() !== integration.name) body.name = draft.name.trim();
    if (draft.model.trim() !== integration.model) body.model = draft.model.trim();
    if (draft.is_default !== integration.is_default) body.is_default = draft.is_default;
    if (draft.api_key_ref.trim()) body.api_key_ref = draft.api_key_ref.trim();

    if (Object.keys(body).length === 0) {
      cancelEditing();
      return;
    }

    patchIntegration.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Integration updated");
          cancelEditing();
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
          backTo="/manage/llm-integrations"
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
        />

        <Tabs defaultValue="configuration">
          <TabsList className="border-b border-border bg-transparent w-full justify-start rounded-none h-auto p-0 gap-0">
            <TabsTrigger
              value="configuration"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-teal data-[state=active]:text-foreground text-dim pb-2 px-4 text-sm"
            >
              <Settings className="h-3.5 w-3.5 mr-1.5" />
              Configuration
            </TabsTrigger>
            <TabsTrigger
              value="usage"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-teal data-[state=active]:text-foreground text-dim pb-2 px-4 text-sm"
            >
              <BarChart3 className="h-3.5 w-3.5 mr-1.5" />
              Usage
            </TabsTrigger>
          </TabsList>

          {/* Configuration Tab */}
          <TabsContent value="configuration" className="pt-6">
            <Card className="border-border bg-card">
              <CardHeader className="flex flex-row items-center justify-between pb-4">
                <CardTitle className="text-sm font-semibold text-foreground">
                  Integration Settings
                </CardTitle>
                {!editing ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-3 text-xs gap-1"
                    onClick={startEditing}
                  >
                    <Pencil className="h-3 w-3" />
                    Edit
                  </Button>
                ) : (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-3 text-xs text-dim gap-1"
                      onClick={cancelEditing}
                      disabled={patchIntegration.isPending}
                    >
                      <X className="h-3 w-3" />
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="h-7 px-3 text-xs bg-teal text-white hover:bg-teal-dim gap-1"
                      onClick={handleSave}
                      disabled={patchIntegration.isPending}
                    >
                      <Save className="h-3 w-3" />
                      {patchIntegration.isPending ? "Saving..." : "Save"}
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Name */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Name</Label>
                  {editing && draft ? (
                    <Input
                      value={draft.name}
                      onChange={(e) => setDraft((d) => d ? { ...d, name: e.target.value } : d)}
                      className="max-w-sm"
                    />
                  ) : (
                    <p className="text-sm text-foreground">{integration.name}</p>
                  )}
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
                  {editing && draft ? (
                    <Input
                      value={draft.model}
                      onChange={(e) => setDraft((d) => d ? { ...d, model: e.target.value } : d)}
                      className="max-w-sm font-mono"
                    />
                  ) : (
                    <p className="text-sm text-foreground font-mono">{integration.model}</p>
                  )}
                </div>

                {/* API Key */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">API Key Env Var</Label>
                  {editing && draft ? (
                    <div className="space-y-1">
                      <Input
                        value={draft.api_key_ref}
                        onChange={(e) => setDraft((d) => d ? { ...d, api_key_ref: e.target.value } : d)}
                        placeholder="e.g. ANTHROPIC_API_KEY (leave blank to keep current)"
                        className="max-w-sm"
                      />
                      <p className="text-xs text-dim">
                        Leave blank to keep the existing key reference.
                      </p>
                    </div>
                  ) : (
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
                  )}
                </div>

                {/* Base URL */}
                {integration.base_url && (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-dim uppercase tracking-wide">Base URL</Label>
                    <p className="text-sm text-foreground font-mono">{integration.base_url}</p>
                  </div>
                )}

                {/* Default toggle */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-dim uppercase tracking-wide">Default Integration</Label>
                  {editing && draft ? (
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
                      <Label
                        htmlFor="edit-is-default"
                        className="cursor-pointer font-normal text-sm"
                      >
                        Use as default LLM integration
                      </Label>
                    </div>
                  ) : (
                    <p className="text-sm text-foreground">
                      {integration.is_default ? "Yes" : "No"}
                    </p>
                  )}
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
    </AppLayout>
  );
}
