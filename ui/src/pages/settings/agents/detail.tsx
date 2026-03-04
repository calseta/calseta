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
import {
  TargetingRuleBuilder,
  TargetingRuleDisplay,
} from "@/components/targeting-rules/targeting-rule-builder";
import {
  type TargetingRules,
  parseTargetingRules,
  serializeTargetingRules,
} from "@/components/targeting-rules/types";
import { useAgent, usePatchAgent, useTestAgent } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import {
  Globe,
  Clock,
  RefreshCw,
  Pencil,
  Save,
  X,
  Send,
  Loader2,
  Lock,
  Shield,
  Zap,
  CheckCircle2,
  XCircle,
  Check,
} from "lucide-react";

const ALL_SEVERITIES = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];
const ALL_SOURCES = ["sentinel", "elastic", "splunk", "generic"];
const TIMEOUT_OPTIONS = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300];
const RETRY_OPTIONS = [0, 1, 2, 3, 4, 5];

export function AgentDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data, isLoading, refetch, isFetching } = useAgent(uuid);
  const patchAgent = usePatchAgent();
  const testAgent = useTestAgent();

  // Trigger editing state (sources/severities: null = clean, non-null = dirty)
  const [sourcesDraft, setSourcesDraft] = useState<string[] | null>(null);
  const [severitiesDraft, setSeveritiesDraft] = useState<string[] | null>(null);
  const [editingFilter, setEditingFilter] = useState(false);
  const [filterDraft, setFilterDraft] = useState<TargetingRules | null>(null);

  // Auth editing state
  const [editingAuth, setEditingAuth] = useState(false);
  const [authHeaderName, setAuthHeaderName] = useState("");
  const [authHeaderValue, setAuthHeaderValue] = useState("");

  // Endpoint editing state
  const [editingEndpoint, setEditingEndpoint] = useState(false);
  const [endpointDraft, setEndpointDraft] = useState("");

  // Test result
  const [testResult, setTestResult] = useState<{
    delivered: boolean;
    status_code: number | null;
    duration_ms: number;
    error: string | null;
  } | null>(null);

  const agent = data?.data;

  if (isLoading) {
    return (
      <AppLayout title="Agent">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!agent) {
    return (
      <AppLayout title="Agent">
        <div className="text-center text-dim py-20">Agent not found</div>
      </AppLayout>
    );
  }

  // --- Status toggle (inline in status card) ---
  function handleStatusChange(value: string) {
    const isActive = value === "active";
    patchAgent.mutate(
      { uuid, body: { is_active: isActive } },
      {
        onSuccess: () => toast.success(isActive ? "Agent activated" : "Agent deactivated"),
        onError: () => toast.error("Failed to update agent status"),
      },
    );
  }

  // --- Endpoint (inline edit in status card) ---
  function startEditingEndpoint() {
    setEndpointDraft(agent!.endpoint_url);
    setEditingEndpoint(true);
  }

  function handleSaveEndpoint() {
    const trimmed = endpointDraft.trim();
    if (!trimmed || trimmed === agent!.endpoint_url) {
      setEditingEndpoint(false);
      return;
    }
    patchAgent.mutate(
      { uuid, body: { endpoint_url: trimmed } },
      {
        onSuccess: () => {
          toast.success("Endpoint updated");
          setEditingEndpoint(false);
        },
        onError: () => toast.error("Failed to update endpoint"),
      },
    );
  }

  function handleEndpointKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSaveEndpoint();
    if (e.key === "Escape") setEditingEndpoint(false);
  }

  // --- Timeout (inline select in status card) ---
  function handleTimeoutChange(value: string) {
    patchAgent.mutate(
      { uuid, body: { timeout_seconds: Number(value) } },
      {
        onSuccess: () => toast.success(`Timeout set to ${value}s`),
        onError: () => toast.error("Failed to update timeout"),
      },
    );
  }

  // --- Retries (inline select in status card) ---
  function handleRetryChange(value: string) {
    patchAgent.mutate(
      { uuid, body: { retry_count: Number(value) } },
      {
        onSuccess: () => toast.success(`Retry count set to ${value}`),
        onError: () => toast.error("Failed to update retry count"),
      },
    );
  }

  // --- Sources & Severities (always-interactive chips, dirty-state pattern) ---
  const triggersDirty = sourcesDraft !== null || severitiesDraft !== null;

  function toggleSource(source: string) {
    const current = sourcesDraft ?? [...agent!.trigger_on_sources];
    const next = current.includes(source)
      ? current.filter((s) => s !== source)
      : [...current, source];
    setSourcesDraft(next);
  }

  function toggleSeverity(sev: string) {
    const current = severitiesDraft ?? [...agent!.trigger_on_severities];
    const next = current.includes(sev)
      ? current.filter((s) => s !== sev)
      : [...current, sev];
    setSeveritiesDraft(next);
  }

  function handleSaveTriggers() {
    const body: Record<string, unknown> = {};
    if (sourcesDraft !== null) body.trigger_on_sources = sourcesDraft;
    if (severitiesDraft !== null) body.trigger_on_severities = severitiesDraft;
    patchAgent.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Trigger configuration updated");
          setSourcesDraft(null);
          setSeveritiesDraft(null);
        },
        onError: () => toast.error("Failed to update trigger configuration"),
      },
    );
  }

  function handleCancelTriggers() {
    setSourcesDraft(null);
    setSeveritiesDraft(null);
  }

  // --- Advanced filter ---
  function startEditingFilter() {
    setFilterDraft(parseTargetingRules(agent!.trigger_filter));
    setEditingFilter(true);
  }

  function handleSaveFilter() {
    const serialized = serializeTargetingRules(filterDraft);
    patchAgent.mutate(
      { uuid, body: { trigger_filter: serialized ?? null } },
      {
        onSuccess: () => {
          toast.success("Advanced trigger rules saved");
          setEditingFilter(false);
        },
        onError: () => toast.error("Failed to save trigger rules"),
      },
    );
  }

  // --- Auth ---
  function startEditingAuth() {
    setAuthHeaderName(agent!.auth_header_name ?? "");
    setAuthHeaderValue("");
    setEditingAuth(true);
  }

  function handleSaveAuth() {
    const body: Record<string, unknown> = {};
    if (authHeaderName.trim()) {
      body.auth_header_name = authHeaderName.trim();
    } else {
      body.auth_header_name = null;
    }
    if (authHeaderValue.trim()) {
      body.auth_header_value = authHeaderValue.trim();
    }
    patchAgent.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Authentication updated");
          setEditingAuth(false);
        },
        onError: () => toast.error("Failed to update authentication"),
      },
    );
  }

  // --- Test webhook ---
  function handleTest() {
    setTestResult(null);
    testAgent.mutate(uuid, {
      onSuccess: (res) => setTestResult(res.data),
      onError: () => toast.error("Failed to send test webhook"),
    });
  }

  // --- Documentation ---
  function handleSaveDocumentation(content: string) {
    patchAgent.mutate(
      { uuid, body: { documentation: content || null } },
      {
        onSuccess: () => toast.success("Documentation saved"),
        onError: () => toast.error("Failed to save documentation"),
      },
    );
  }

  return (
    <AppLayout title="Agent Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/settings/agents"
          title={agent.name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  agent.is_active
                    ? "text-teal bg-teal/10 border-teal/30"
                    : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {agent.is_active ? "active" : "inactive"}
              </Badge>
            </>
          }
          subtitle={
            agent.description ? (
              <p className="text-sm text-muted-foreground">{agent.description}</p>
            ) : undefined
          }
        />

        {/* Inline-editable status cards (consistent with alerts detail) */}
        <DetailPageStatusCards
          items={[
            {
              label: "Status",
              icon: Shield,
              value: (
                <Select
                  value={agent.is_active ? "active" : "inactive"}
                  onValueChange={handleStatusChange}
                >
                  <SelectTrigger
                    className={cn(
                      "h-7 w-full text-xs border",
                      agent.is_active
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
              label: "Endpoint",
              icon: Globe,
              value: editingEndpoint ? (
                <div className="flex items-center gap-1">
                  <Input
                    value={endpointDraft}
                    onChange={(e) => setEndpointDraft(e.target.value)}
                    onKeyDown={handleEndpointKeyDown}
                    onBlur={handleSaveEndpoint}
                    autoFocus
                    className="h-7 text-xs font-mono bg-surface border-border"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSaveEndpoint}
                    className="h-7 w-7 p-0 text-teal shrink-0"
                  >
                    <Check className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <button
                  onClick={startEditingEndpoint}
                  className="group flex items-center gap-1.5 w-full text-left"
                >
                  <span className="font-mono text-xs truncate">
                    {agent.endpoint_url}
                  </span>
                  <Pencil className="h-3 w-3 text-dim opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                </button>
              ),
            },
            {
              label: "Timeout",
              icon: Clock,
              value: (
                <Select
                  value={String(agent.timeout_seconds)}
                  onValueChange={handleTimeoutChange}
                >
                  <SelectTrigger className="h-7 w-full text-xs border border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {TIMEOUT_OPTIONS.map((t) => (
                      <SelectItem key={t} value={String(t)}>
                        {t}s
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Retries",
              icon: RefreshCw,
              value: (
                <Select
                  value={String(agent.retry_count)}
                  onValueChange={handleRetryChange}
                >
                  <SelectTrigger className="h-7 w-full text-xs border border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {RETRY_OPTIONS.map((r) => (
                      <SelectItem key={r} value={String(r)}>
                        {r}
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
                  value={<CopyableText text={agent.uuid} mono className="text-xs" />}
                />
                <DetailPageField label="Name" value={agent.name} />
                <DetailPageField
                  label="Endpoint"
                  value={<CopyableText text={agent.endpoint_url} mono className="text-xs" />}
                />
                <DetailPageField
                  label="Auth Header"
                  value={agent.auth_header_name ? (
                    <span className="font-mono">{agent.auth_header_name}</span>
                  ) : (
                    <span className="text-dim">Not set</span>
                  )}
                />
                <DetailPageField label="Created" value={formatDate(agent.created_at)} />
                <DetailPageField label="Updated" value={formatDate(agent.updated_at)} />
              </SidebarSection>
            </DetailPageSidebar>
          }
        >
          <div className="space-y-6">
            {/* Trigger Configuration (unified card) */}
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <Zap className="h-3.5 w-3.5 text-teal" />
                    Trigger Configuration
                  </div>
                </CardTitle>
                {triggersDirty && (
                  <div className="flex gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleCancelTriggers}
                      className="h-7 text-xs text-dim"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSaveTriggers}
                      disabled={patchAgent.isPending}
                      className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                    >
                      {patchAgent.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <Save className="h-3 w-3 mr-1" />
                      )}
                      Save
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent className="space-y-5">
                {/* Sources */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Sources</span>
                    <span className="text-[11px] text-dim">None selected = all sources</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {ALL_SOURCES.map((source) => {
                      const effective = sourcesDraft ?? agent.trigger_on_sources;
                      const selected = effective.includes(source);
                      return (
                        <button
                          key={source}
                          type="button"
                          onClick={() => toggleSource(source)}
                          className={cn(
                            "px-3 py-1.5 rounded-md text-xs border transition-colors",
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

                <div className="border-t border-border" />

                {/* Severities */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Severities</span>
                    <span className="text-[11px] text-dim">None selected = all severities</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {ALL_SEVERITIES.map((sev) => {
                      const effective = severitiesDraft ?? agent.trigger_on_severities;
                      const selected = effective.includes(sev);
                      return (
                        <button
                          key={sev}
                          type="button"
                          onClick={() => toggleSeverity(sev)}
                          className={cn(
                            "px-3 py-1.5 rounded-md text-xs border transition-colors",
                            selected
                              ? "bg-teal/15 border-teal/40 text-teal-light"
                              : "bg-surface border-border text-dim hover:border-teal/30",
                          )}
                        >
                          {sev}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="border-t border-border" />

                {/* Advanced Rules (subsection with own edit/save toggle) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Advanced Rules</span>
                      <p className="text-[11px] text-dim mt-0.5">
                        Match_any (OR) and match_all (AND) conditions against alert fields.
                      </p>
                    </div>
                    {!editingFilter ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={startEditingFilter}
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
                          onClick={() => setEditingFilter(false)}
                          className="h-7 text-xs text-dim"
                        >
                          <X className="h-3 w-3 mr-1" />
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleSaveFilter}
                          disabled={patchAgent.isPending}
                          className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                        >
                          <Save className="h-3 w-3 mr-1" />
                          Save
                        </Button>
                      </div>
                    )}
                  </div>
                  {editingFilter ? (
                    <TargetingRuleBuilder value={filterDraft} onChange={setFilterDraft} />
                  ) : (
                    <TargetingRuleDisplay rules={agent.trigger_filter} />
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Authentication */}
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <Lock className="h-3.5 w-3.5 text-dim" />
                    Authentication
                  </div>
                </CardTitle>
                {!editingAuth ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={startEditingAuth}
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
                      onClick={() => setEditingAuth(false)}
                      className="h-7 text-xs text-dim"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSaveAuth}
                      disabled={patchAgent.isPending}
                      className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                    >
                      <Save className="h-3 w-3 mr-1" />
                      Save
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {editingAuth ? (
                  <div className="space-y-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">Header Name</Label>
                      <Input
                        value={authHeaderName}
                        onChange={(e) => setAuthHeaderName(e.target.value)}
                        placeholder="e.g. Authorization, X-API-Key"
                        className="mt-1 bg-surface border-border text-sm font-mono"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">Header Value</Label>
                      <Input
                        type="password"
                        value={authHeaderValue}
                        onChange={(e) => setAuthHeaderValue(e.target.value)}
                        placeholder="Leave empty to keep current value"
                        className="mt-1 bg-surface border-border text-sm"
                      />
                      <p className="text-[11px] text-dim mt-1">
                        The value is encrypted at rest. Leave empty to keep the existing value.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Header Name</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.auth_header_name || "Not set"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Header Value</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[11px]",
                          agent.auth_header_name
                            ? "text-teal border-teal/30"
                            : "text-dim border-border",
                        )}
                      >
                        {agent.auth_header_name ? "configured" : "not set"}
                      </Badge>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Test Webhook */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <Send className="h-3.5 w-3.5 text-dim" />
                    Test Webhook
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-dim mb-3">
                  Send a test payload to the agent endpoint to verify connectivity and authentication.
                </p>
                <div className="flex items-center gap-3">
                  <Button
                    size="sm"
                    onClick={handleTest}
                    disabled={testAgent.isPending}
                    className="bg-teal text-white hover:bg-teal-dim text-xs"
                  >
                    {testAgent.isPending ? (
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    ) : (
                      <Send className="h-3 w-3 mr-1" />
                    )}
                    Send Test
                  </Button>
                  {testResult && (
                    <div className="flex items-center gap-3">
                      {testResult.delivered ? (
                        <Badge variant="outline" className="text-xs text-teal border-teal/30 bg-teal/10">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Delivered
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs text-red-threat border-red-threat/30 bg-red-threat/10">
                          <XCircle className="h-3 w-3 mr-1" />
                          Failed
                        </Badge>
                      )}
                      {testResult.status_code !== null && (
                        <span className="text-xs text-dim font-mono">
                          HTTP {testResult.status_code}
                        </span>
                      )}
                      <span className="text-xs text-dim">
                        {testResult.duration_ms}ms
                      </span>
                    </div>
                  )}
                </div>
                {testResult?.error && (
                  <div className="mt-3 rounded-md bg-red-threat/5 border border-red-threat/20 p-3">
                    <p className="text-xs text-red-threat font-mono">{testResult.error}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Documentation */}
            <DocumentationEditor
              content={agent.documentation ?? ""}
              onSave={handleSaveDocumentation}
              isSaving={patchAgent.isPending}
            />
          </div>
        </DetailPageLayout>
      </div>
    </AppLayout>
  );
}
