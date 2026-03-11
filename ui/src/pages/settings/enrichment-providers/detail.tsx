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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
  DocumentationEditor,
} from "@/components/detail-page";
import { CopyableText } from "@/components/copyable-text";
import { JsonViewer } from "@/components/json-viewer";
import {
  HttpConfigBuilder,
  HttpConfigDisplay,
  parseHttpConfig,
} from "@/components/http-config-builder";
import type { HttpConfig } from "@/components/http-config-builder";
import {
  MaliceRulesBuilder,
  MaliceRulesDisplay,
  parseMaliceRules,
} from "@/components/malice-rules-builder";
import type { MaliceRules } from "@/components/malice-rules-builder";
import {
  useEnrichmentProvider,
  usePatchEnrichmentProvider,
  useActivateEnrichmentProvider,
  useDeactivateEnrichmentProvider,
  useTestEnrichmentProvider,
  useDeleteEnrichmentProvider,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { FieldExtractionEditor } from "@/components/field-extraction-editor";
import { useNavigate } from "@tanstack/react-router";
import { INDICATOR_TYPES as ALL_INDICATOR_TYPES } from "@/lib/types";
import type { HttpStepDebug, EnrichmentProviderTestResult } from "@/lib/types";
import {
  Shield,
  Globe,
  Clock,
  Pencil,
  Save,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Beaker,
  FileCode2,
  Scale,
  Trash2,
  Microscope,
  ChevronDown,
  ChevronRight,
  FileText,
} from "lucide-react";


const CACHE_TTL_OPTIONS = [
  { value: "300", label: "5 min" },
  { value: "900", label: "15 min" },
  { value: "1800", label: "30 min" },
  { value: "3600", label: "1 hour" },
  { value: "7200", label: "2 hours" },
  { value: "14400", label: "4 hours" },
  { value: "86400", label: "24 hours" },
];

// ---------------------------------------------------------------------------
// Test Result Display (Postman-style step viewer)
// ---------------------------------------------------------------------------

function StatusCodeBadge({ code }: { code: number }) {
  const isOk = code >= 200 && code < 300;
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-xs font-mono",
        isOk
          ? "text-teal border-teal/30 bg-teal/10"
          : "text-red-threat border-red-threat/30 bg-red-threat/10",
      )}
    >
      {code}
    </Badge>
  );
}

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET: "text-blue-400 border-blue-400/30 bg-blue-400/10",
    POST: "text-teal border-teal/30 bg-teal/10",
    PUT: "text-amber-400 border-amber-400/30 bg-amber-400/10",
    PATCH: "text-amber-400 border-amber-400/30 bg-amber-400/10",
    DELETE: "text-red-threat border-red-threat/30 bg-red-threat/10",
  };
  return (
    <Badge variant="outline" className={cn("text-xs font-mono font-bold", colors[method] || "text-dim border-border")}>
      {method}
    </Badge>
  );
}

function HeadersGrid({ headers }: { headers: Record<string, string> }) {
  const entries = Object.entries(headers);
  if (entries.length === 0) return <span className="text-xs text-dim">No headers</span>;
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <span className="text-xs font-mono text-muted-foreground truncate">{key}</span>
          <span className="text-xs font-mono text-foreground truncate">{value}</span>
        </div>
      ))}
    </div>
  );
}

function StepDetail({ step }: { step: HttpStepDebug }) {
  return (
    <div className="space-y-4 pt-3 pb-1">
      {/* Request Headers */}
      {Object.keys(step.request_headers).length > 0 && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Request Headers</span>
          <div className="mt-1.5 p-2.5 rounded-md bg-surface border border-border">
            <HeadersGrid headers={step.request_headers} />
          </div>
        </div>
      )}

      {/* Request Query Params */}
      {step.request_query_params && Object.keys(step.request_query_params).length > 0 && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Query Parameters</span>
          <div className="mt-1.5 p-2.5 rounded-md bg-surface border border-border">
            <HeadersGrid headers={step.request_query_params} />
          </div>
        </div>
      )}

      {/* Request Body */}
      {step.request_body != null && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Request Body</span>
          <div className="mt-1.5">
            <JsonViewer data={step.request_body as Record<string, unknown>} defaultExpanded={2} />
          </div>
        </div>
      )}

      {/* Error */}
      {step.error && (
        <div className="rounded-md bg-red-threat/5 border border-red-threat/20 p-3">
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium block mb-1">Error</span>
          <p className="text-xs text-red-threat font-mono">{step.error}</p>
        </div>
      )}

      {/* Response Headers */}
      {step.response_headers && Object.keys(step.response_headers).length > 0 && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Response Headers</span>
          <div className="mt-1.5 p-2.5 rounded-md bg-surface border border-border">
            <HeadersGrid headers={step.response_headers} />
          </div>
        </div>
      )}

      {/* Response Body */}
      {step.response_body != null && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Response Body</span>
          <div className="mt-1.5">
            <JsonViewer data={step.response_body as Record<string, unknown>} defaultExpanded={2} />
          </div>
        </div>
      )}
    </div>
  );
}

function TestResultDisplay({
  result,
  expandedSteps,
  onToggleStep,
}: {
  result: EnrichmentProviderTestResult;
  expandedSteps: Set<number>;
  onToggleStep: (idx: number) => void;
}) {
  return (
    <div className="space-y-3 mt-3">
      {/* Summary bar */}
      <div className="flex items-center gap-3">
        {result.success ? (
          <Badge variant="outline" className="text-xs text-teal border-teal/30 bg-teal/10">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Success
          </Badge>
        ) : (
          <Badge variant="outline" className="text-xs text-red-threat border-red-threat/30 bg-red-threat/10">
            <XCircle className="h-3 w-3 mr-1" />
            Failed
          </Badge>
        )}
        <span className="text-xs text-dim">{result.duration_ms}ms</span>
        {result.steps && result.steps.length > 0 && (
          <span className="text-xs text-dim">
            {result.steps.length} step{result.steps.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Error message (top-level) */}
      {result.error_message && !result.steps?.length && (
        <div className="rounded-md bg-red-threat/5 border border-red-threat/20 p-3">
          <p className="text-xs text-red-threat font-mono">{result.error_message}</p>
        </div>
      )}

      {/* Steps */}
      {result.steps && result.steps.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            HTTP Steps
          </span>
          <div className="space-y-1.5">
            {result.steps.map((step, idx) => {
              const isExpanded = expandedSteps.has(idx);
              return (
                <div key={idx} className="rounded-md border border-border bg-surface overflow-hidden">
                  <button
                    type="button"
                    onClick={() => onToggleStep(idx)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/30 transition-colors"
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5 text-dim shrink-0" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 text-dim shrink-0" />
                    )}
                    <MethodBadge method={step.request_method} />
                    <span className="text-xs font-mono text-foreground truncate flex-1">
                      {step.request_url}
                    </span>
                    {step.response_status_code != null && (
                      <StatusCodeBadge code={step.response_status_code} />
                    )}
                    {step.error && !step.response_status_code && (
                      <Badge variant="outline" className="text-xs text-red-threat border-red-threat/30 bg-red-threat/10">
                        Error
                      </Badge>
                    )}
                    {step.skipped && (
                      <Badge variant="outline" className="text-xs text-dim border-border">
                        Skipped
                      </Badge>
                    )}
                    <span className="text-xs text-dim shrink-0">{step.duration_ms}ms</span>
                  </button>
                  {isExpanded && (
                    <div className="px-3 pb-3 border-t border-border">
                      <StepDetail step={step} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Extracted Data */}
      {result.extracted && Object.keys(result.extracted).length > 0 && (
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Extracted Fields
          </span>
          <div className="mt-2">
            <JsonViewer data={result.extracted} defaultExpanded={3} />
          </div>
        </div>
      )}
    </div>
  );
}

export function EnrichmentProviderDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data, isLoading, refetch, isFetching } = useEnrichmentProvider(uuid);
  const patchProvider = usePatchEnrichmentProvider();
  const activateProvider = useActivateEnrichmentProvider();
  const deactivateProvider = useDeactivateEnrichmentProvider();
  const testProvider = useTestEnrichmentProvider();
  const deleteProvider = useDeleteEnrichmentProvider();
  const navigate = useNavigate();

  // Indicator types editing (dirty-state)
  const [indicatorTypesDraft, setIndicatorTypesDraft] = useState<string[] | null>(null);

  // HTTP config editing state (custom only)
  const [editingHttpConfig, setEditingHttpConfig] = useState(false);
  const [httpConfigDraftObj, setHttpConfigDraftObj] = useState<HttpConfig>({ steps: [] });

  // Malice rules editing state
  const [editingMaliceRules, setEditingMaliceRules] = useState(false);
  const [maliceRulesDraftObj, setMaliceRulesDraftObj] = useState<MaliceRules>({
    rules: [],
    default_verdict: "Pending",
    not_found_verdict: "Pending",
  });

  // Test state
  const [testIndicatorType, setTestIndicatorType] = useState("ip");
  const [testIndicatorValue, setTestIndicatorValue] = useState("");
  const [testResult, setTestResult] = useState<EnrichmentProviderTestResult | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  // Delete state
  const [showDelete, setShowDelete] = useState(false);

  const provider = data?.data;

  if (isLoading) {
    return (
      <AppLayout title="Enrichment Provider">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!provider) {
    return (
      <AppLayout title="Enrichment Provider">
        <div className="text-center text-dim py-20">Provider not found</div>
      </AppLayout>
    );
  }

  // --- Status toggle ---
  function handleStatusChange(value: string) {
    if (value === "active") {
      activateProvider.mutate(uuid, {
        onSuccess: () => toast.success("Provider activated"),
        onError: () => toast.error("Failed to activate provider"),
      });
    } else {
      deactivateProvider.mutate(uuid, {
        onSuccess: () => toast.success("Provider deactivated"),
        onError: () => toast.error("Failed to deactivate provider"),
      });
    }
  }

  // --- Cache TTL ---
  function handleCacheTtlChange(value: string) {
    patchProvider.mutate(
      { uuid, body: { default_cache_ttl_seconds: Number(value) } },
      {
        onSuccess: () => toast.success(`Cache TTL set to ${value}s`),
        onError: () => toast.error("Failed to update cache TTL"),
      },
    );
  }

  // --- Indicator Types (dirty-state chips) ---
  const indicatorTypesDirty = indicatorTypesDraft !== null;

  function toggleIndicatorType(type: string) {
    const current = indicatorTypesDraft ?? [...provider!.supported_indicator_types];
    const next = current.includes(type)
      ? current.filter((t) => t !== type)
      : [...current, type];
    setIndicatorTypesDraft(next);
  }

  function handleSaveIndicatorTypes() {
    if (indicatorTypesDraft === null) return;
    patchProvider.mutate(
      { uuid, body: { supported_indicator_types: indicatorTypesDraft } },
      {
        onSuccess: () => {
          toast.success("Indicator types updated");
          setIndicatorTypesDraft(null);
        },
        onError: () => toast.error("Failed to update indicator types"),
      },
    );
  }

  // --- HTTP Config (custom only) ---
  function startEditingHttpConfig() {
    const parsed = parseHttpConfig(provider!.http_config);
    setHttpConfigDraftObj(parsed ?? { steps: [] });
    setEditingHttpConfig(true);
  }

  function handleSaveHttpConfig() {
    patchProvider.mutate(
      { uuid, body: { http_config: httpConfigDraftObj as unknown as Record<string, unknown> } },
      {
        onSuccess: () => {
          toast.success("HTTP configuration updated");
          setEditingHttpConfig(false);
        },
        onError: () => toast.error("Failed to update HTTP configuration"),
      },
    );
  }

  // --- Malice Rules ---
  function startEditingMaliceRules() {
    const parsed = parseMaliceRules(provider!.malice_rules);
    setMaliceRulesDraftObj(
      parsed ?? { rules: [], default_verdict: "Pending", not_found_verdict: "Pending" },
    );
    setEditingMaliceRules(true);
  }

  function handleSaveMaliceRules() {
    patchProvider.mutate(
      { uuid, body: { malice_rules: maliceRulesDraftObj as unknown as Record<string, unknown> } },
      {
        onSuccess: () => {
          toast.success("Malice rules updated");
          setEditingMaliceRules(false);
        },
        onError: () => toast.error("Failed to update malice rules"),
      },
    );
  }

  // --- Test ---
  function handleTest() {
    if (!testIndicatorValue.trim()) {
      toast.error("Enter an indicator value");
      return;
    }
    setTestResult(null);
    setExpandedSteps(new Set());
    testProvider.mutate(
      { uuid, body: { indicator_type: testIndicatorType, indicator_value: testIndicatorValue.trim() } },
      {
        onSuccess: (res) => {
          setTestResult(res.data);
          // Auto-expand all steps for single-step providers, first step for multi-step
          const steps = res.data.steps;
          if (steps && steps.length === 1) {
            setExpandedSteps(new Set([0]));
          } else if (steps && steps.length > 0) {
            setExpandedSteps(new Set([0]));
          }
        },
        onError: () => toast.error("Failed to test provider"),
      },
    );
  }

  // --- Delete ---
  function handleDelete() {
    deleteProvider.mutate(uuid, {
      onSuccess: () => {
        toast.success("Provider deleted");
        navigate({ to: "/manage/enrichment-providers" });
      },
      onError: () => toast.error("Failed to delete provider"),
    });
  }

  // --- Documentation ---
  function handleSaveDocumentation(content: string) {
    patchProvider.mutate(
      { uuid, body: { description: content || null } },
      {
        onSuccess: () => toast.success("Description saved"),
        onError: () => toast.error("Failed to save description"),
      },
    );
  }

  return (
    <AppLayout title="Enrichment Provider">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/enrichment-providers"
          title={provider.display_name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  provider.is_builtin
                    ? "text-muted-foreground bg-muted/50 border-muted"
                    : "text-teal-light bg-teal-light/10 border-teal-light/30",
                )}
              >
                {provider.is_builtin ? "builtin" : "custom"}
              </Badge>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  provider.is_active
                    ? "text-teal bg-teal/10 border-teal/30"
                    : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {provider.is_active ? "active" : "inactive"}
              </Badge>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  provider.is_configured
                    ? "text-teal border-teal/30"
                    : "text-dim border-border",
                )}
              >
                {provider.is_configured ? "configured" : "not configured"}
              </Badge>
            </>
          }
          subtitle={
            provider.description ? (
              <p className="text-sm text-muted-foreground">{provider.description}</p>
            ) : undefined
          }
          actions={
            !provider.is_builtin ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDelete(true)}
                className="text-dim hover:text-red-threat"
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Delete
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
                <Select
                  value={provider.is_active ? "active" : "inactive"}
                  onValueChange={handleStatusChange}
                >
                  <SelectTrigger
                    className={cn(
                      "h-7 w-full text-xs border",
                      provider.is_active
                        ? "text-teal bg-teal/10 border-teal/30"
                        : "text-dim bg-dim/10 border-dim/30",
                    )}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Configured",
              icon: Globe,
              value: (
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    provider.is_configured
                      ? "text-teal border-teal/30 bg-teal/10"
                      : "text-dim border-border",
                  )}
                >
                  {provider.is_configured ? "yes" : "no"}
                </Badge>
              ),
            },
            {
              label: "Cache TTL",
              icon: Clock,
              value: (
                <Select
                  value={String(provider.default_cache_ttl_seconds)}
                  onValueChange={handleCacheTtlChange}
                >
                  <SelectTrigger className="h-7 w-full text-xs border border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {CACHE_TTL_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ),
            },
          ]}
        />

        <DetailPageLayout
          sidebar={
            <DetailPageSidebar>
              <SidebarSection title="Details">
                <DetailPageField
                  label="UUID"
                  value={<CopyableText text={provider.uuid} mono className="text-xs" />}
                />
                <DetailPageField
                  label="Provider Name"
                  value={<span className="font-mono text-xs">{provider.provider_name}</span>}
                />
                <DetailPageField
                  label="Cache TTL"
                  value={`${provider.default_cache_ttl_seconds}s`}
                />
                <DetailPageField label="Created" value={formatDate(provider.created_at)} />
                <DetailPageField label="Updated" value={formatDate(provider.updated_at)} />
              </SidebarSection>

              {provider.env_var_mapping && Object.keys(provider.env_var_mapping).length > 0 && (
                <SidebarSection title="Env Variables">
                  {Object.entries(provider.env_var_mapping).map(([key, envVar]) => (
                    <DetailPageField key={key} label={key} value={<span className="font-mono text-xs">{envVar}</span>} />
                  ))}
                </SidebarSection>
              )}

              {provider.cache_ttl_by_type && Object.keys(provider.cache_ttl_by_type).length > 0 && (
                <SidebarSection title="Cache TTL by Type">
                  {Object.entries(provider.cache_ttl_by_type).map(([type, ttl]) => (
                    <DetailPageField key={type} label={type} value={`${ttl}s`} />
                  ))}
                </SidebarSection>
              )}
            </DetailPageSidebar>
          }
        >
          <Tabs defaultValue="configuration" className="w-full">
            <TabsList className="bg-surface border border-border">
              <TabsTrigger value="configuration" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Configuration
              </TabsTrigger>
              <TabsTrigger value="extractions" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Field Extractions
              </TabsTrigger>
              <TabsTrigger value="test" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Test
              </TabsTrigger>
              <TabsTrigger value="docs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <FileText className="h-3.5 w-3.5 mr-1" />
                Documentation
              </TabsTrigger>
            </TabsList>

            {/* Configuration Tab */}
            <TabsContent value="configuration" className="space-y-6 mt-4">
              {/* Supported Indicator Types */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Microscope className="h-3.5 w-3.5 text-teal" />
                      Supported Indicator Types
                    </div>
                  </CardTitle>
                  {indicatorTypesDirty && !provider.is_builtin && (
                    <div className="flex gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setIndicatorTypesDraft(null)}
                        className="h-7 text-xs text-dim"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveIndicatorTypes}
                        disabled={patchProvider.isPending}
                        className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                      >
                        {patchProvider.isPending ? (
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        ) : (
                          <Save className="h-3 w-3 mr-1" />
                        )}
                        Save
                      </Button>
                    </div>
                  )}
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {ALL_INDICATOR_TYPES.map((type) => {
                      const effective = indicatorTypesDraft ?? provider.supported_indicator_types;
                      const selected = effective.includes(type);

                      if (provider.is_builtin) {
                        return (
                          <span
                            key={type}
                            className={cn(
                              "px-3 py-1.5 rounded-md text-xs border",
                              selected
                                ? "bg-teal/15 border-teal/40 text-teal-light"
                                : "bg-surface border-border text-dim",
                            )}
                          >
                            {type}
                          </span>
                        );
                      }

                      return (
                        <button
                          key={type}
                          type="button"
                          onClick={() => toggleIndicatorType(type)}
                          className={cn(
                            "px-3 py-1.5 rounded-md text-xs border transition-colors",
                            selected
                              ? "bg-teal/15 border-teal/40 text-teal-light"
                              : "bg-surface border-border text-dim hover:border-teal/30",
                          )}
                        >
                          {type}
                        </button>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* HTTP Configuration */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <FileCode2 className="h-3.5 w-3.5 text-dim" />
                      HTTP Configuration
                    </div>
                  </CardTitle>
                  {!provider.is_builtin && (
                    !editingHttpConfig ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={startEditingHttpConfig}
                        className="h-7 text-xs text-dim hover:text-teal"
                      >
                        <Pencil className="h-3 w-3 mr-1" />
                        Edit
                      </Button>
                    ) : (
                      <div className="flex gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingHttpConfig(false)}
                          className="h-7 text-xs text-dim"
                        >
                          <X className="h-3 w-3 mr-1" />
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleSaveHttpConfig}
                          disabled={patchProvider.isPending}
                          className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                        >
                          <Save className="h-3 w-3 mr-1" />
                          Save
                        </Button>
                      </div>
                    )
                  )}
                </CardHeader>
                <CardContent>
                  {editingHttpConfig ? (
                    <HttpConfigBuilder
                      value={httpConfigDraftObj}
                      onChange={setHttpConfigDraftObj}
                    />
                  ) : (
                    <HttpConfigDisplay config={provider.http_config} />
                  )}
                </CardContent>
              </Card>

              {/* Malice Rules */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Scale className="h-3.5 w-3.5 text-dim" />
                      Malice Rules
                    </div>
                  </CardTitle>
                  {!editingMaliceRules ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={startEditingMaliceRules}
                      className="h-7 text-xs text-dim hover:text-teal"
                    >
                      <Pencil className="h-3 w-3 mr-1" />
                      Edit
                    </Button>
                  ) : (
                    <div className="flex gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingMaliceRules(false)}
                        className="h-7 text-xs text-dim"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveMaliceRules}
                        disabled={patchProvider.isPending}
                        className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                      >
                        <Save className="h-3 w-3 mr-1" />
                        Save
                      </Button>
                    </div>
                  )}
                </CardHeader>
                <CardContent>
                  {editingMaliceRules ? (
                    <MaliceRulesBuilder
                      value={maliceRulesDraftObj}
                      onChange={setMaliceRulesDraftObj}
                    />
                  ) : (
                    <MaliceRulesDisplay rules={provider.malice_rules} />
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Field Extractions Tab */}
            <TabsContent value="extractions" className="mt-4">
              <FieldExtractionEditor
                providerName={provider.provider_name}
                supportedIndicatorTypes={provider.supported_indicator_types}
                isBuiltin={provider.is_builtin}
              />
            </TabsContent>

            {/* Test Tab */}
            <TabsContent value="test" className="mt-4">
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Beaker className="h-3.5 w-3.5 text-dim" />
                      Test Provider
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-xs text-dim">
                    Test this enrichment provider with a sample indicator to verify connectivity and configuration.
                  </p>
                  <div className="flex items-end gap-3">
                    <div className="w-40">
                      <Label className="text-xs text-muted-foreground">Indicator Type</Label>
                      <Select value={testIndicatorType} onValueChange={setTestIndicatorType}>
                        <SelectTrigger className="mt-1 h-8 bg-surface border-border text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-card border-border">
                          {ALL_INDICATOR_TYPES.map((type) => (
                            <SelectItem key={type} value={type}>{type}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex-1">
                      <Label className="text-xs text-muted-foreground">Indicator Value</Label>
                      <Input
                        value={testIndicatorValue}
                        onChange={(e) => setTestIndicatorValue(e.target.value)}
                        placeholder="e.g. 8.8.8.8, evil.com, abc123..."
                        className="mt-1 h-8 bg-surface border-border text-sm font-mono"
                        onKeyDown={(e) => e.key === "Enter" && handleTest()}
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={handleTest}
                      disabled={testProvider.isPending}
                      className="bg-teal text-white hover:bg-teal-dim text-xs h-8"
                    >
                      {testProvider.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <Beaker className="h-3 w-3 mr-1" />
                      )}
                      Run Test
                    </Button>
                  </div>

                  {testResult && (
                    <TestResultDisplay
                      result={testResult}
                      expandedSteps={expandedSteps}
                      onToggleStep={(idx) => {
                        setExpandedSteps((prev) => {
                          const next = new Set(prev);
                          if (next.has(idx)) next.delete(idx);
                          else next.add(idx);
                          return next;
                        });
                      }}
                    />
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Documentation Tab */}
            <TabsContent value="docs" className="mt-4">
              <DocumentationEditor
                content={provider.description ?? ""}
                onSave={handleSaveDocumentation}
                isSaving={patchProvider.isPending}
              />
            </TabsContent>
          </Tabs>
        </DetailPageLayout>
      </div>

      <ConfirmDialog
        open={showDelete}
        onOpenChange={setShowDelete}
        title="Delete Enrichment Provider"
        description={`Are you sure you want to delete "${provider.display_name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
