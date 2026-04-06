import { useState } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
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
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useAgent,
  usePatchAgent,
  useTestAgent,
  useAgentHeartbeatRuns,
  useAgentCostEvents,
  useAgentInvocations,
  usePauseAgent,
  useResumeAgent,
  useTerminateAgent,
  useTools,
  useAgentActivity,
  useAgentCostSummary,
} from "@/hooks/use-api";
import type { HeartbeatRun, CostEvent, AgentInvocation, AgentTool } from "@/lib/types";
import { formatDate, relativeTime } from "@/lib/format";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  FileText,
  Settings,
  Activity,
  DollarSign,
  Layers,
  Pause,
  Play,
  StopCircle,
  Trash2,
  Plus,
  Wrench,
  LayoutDashboard,
} from "lucide-react";

const ALL_SEVERITIES = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];
const ALL_SOURCES = ["sentinel", "elastic", "splunk", "generic"];
const TIMEOUT_OPTIONS = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300];
const RETRY_OPTIONS = [0, 1, 2, 3, 4, 5];

function heartbeatStatusClass(status: string): string {
  switch (status) {
    case "succeeded": return "text-teal bg-teal/10 border-teal/30";
    case "failed": return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "running": return "text-amber bg-amber/10 border-amber/30";
    default: return "text-dim bg-dim/10 border-dim/30";
  }
}

function invocationStatusClass(status: string): string {
  switch (status) {
    case "completed": return "text-teal bg-teal/10 border-teal/30";
    case "running": return "text-amber bg-amber/10 border-amber/30";
    case "failed":
    case "timed_out": return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default: return "text-dim bg-dim/10 border-dim/30";
  }
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt || !finishedAt) return "--";
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}m`;
}

const HEARTBEAT_COLUMNS: ColumnDef[] = [
  { key: "status", initialWidth: 110 },
  { key: "started_at", initialWidth: 160 },
  { key: "duration", initialWidth: 100 },
  { key: "alerts_processed", initialWidth: 130 },
  { key: "actions_proposed", initialWidth: 140 },
];

const COST_COLUMNS: ColumnDef[] = [
  { key: "provider", initialWidth: 120 },
  { key: "model", initialWidth: 180 },
  { key: "input_tokens", initialWidth: 110 },
  { key: "output_tokens", initialWidth: 120 },
  { key: "cost", initialWidth: 90 },
  { key: "billing_type", initialWidth: 120 },
  { key: "occurred_at", initialWidth: 160 },
];

const INVOCATION_COLUMNS: ColumnDef[] = [
  { key: "task_description", initialWidth: 280 },
  { key: "status", initialWidth: 110 },
  { key: "cost", initialWidth: 90 },
  { key: "started_at", initialWidth: 160 },
  { key: "completed_at", initialWidth: 160 },
];

export function AgentDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { tab: activeTab } = useSearch({ from: "/manage/agents/$uuid" });
  const navigate = useNavigate({ from: "/manage/agents/$uuid" });
  const { data, isLoading, refetch, isFetching } = useAgent(uuid);
  const patchAgent = usePatchAgent();
  const testAgent = useTestAgent();
  const pauseAgent = usePauseAgent();
  const resumeAgent = useResumeAgent();
  const terminateAgent = useTerminateAgent();

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

  // Terminate confirm
  const [showTerminateConfirm, setShowTerminateConfirm] = useState(false);

  // Heartbeat expand state
  const [expandedHeartbeat, setExpandedHeartbeat] = useState<string | null>(null);

  // Test result
  const [testResult, setTestResult] = useState<{
    delivered: boolean;
    status_code: number | null;
    duration_ms: number;
    error: string | null;
  } | null>(null);

  const agent = data?.data;

  // Data for existing tabs
  const { data: heartbeatData } = useAgentHeartbeatRuns(uuid);
  const { data: costData } = useAgentCostEvents(uuid);
  const { data: invocationData } = useAgentInvocations(uuid);

  const heartbeatRuns: HeartbeatRun[] = heartbeatData?.data ?? [];
  const costEvents: CostEvent[] = costData?.data ?? [];
  const invocations: AgentInvocation[] = invocationData?.data ?? [];

  // Instructions tab state
  const [selectedInstructionFile, setSelectedInstructionFile] = useState<string | null>(null);
  const [showNewFileInput, setShowNewFileInput] = useState(false);
  const [newFileName, setNewFileName] = useState("");

  // Skills tab state
  const [showAddToolDialog, setShowAddToolDialog] = useState(false);
  const { data: allToolsData } = useTools();
  const allTools: AgentTool[] = allToolsData?.data ?? [];

  // Dashboard tab
  const { data: costSummaryData } = useAgentCostSummary(uuid);
  const { data: activityData, isError: activityError } = useAgentActivity(uuid);

  const totalCostCents = costEvents.reduce((sum, e) => sum + e.cost_cents, 0);

  function setActiveTab(tab: string) {
    navigate({ search: { tab }, replace: true });
  }

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
    if (value === "active") {
      resumeAgent.mutate(uuid, {
        onSuccess: () => toast.success("Agent resumed"),
        onError: () => toast.error("Failed to resume agent"),
      });
    } else if (value === "paused") {
      pauseAgent.mutate(
        { uuid },
        {
          onSuccess: () => toast.success("Agent paused"),
          onError: () => toast.error("Failed to pause agent"),
        },
      );
    } else if (value === "terminated") {
      setShowTerminateConfirm(true);
    }
  }

  // --- Endpoint (inline edit in status card) ---
  function startEditingEndpoint() {
    setEndpointDraft(agent!.endpoint_url ?? "");
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

  // --- Pause / Resume / Terminate ---
  function handlePause() {
    pauseAgent.mutate(
      { uuid },
      {
        onSuccess: () => toast.success("Agent paused"),
        onError: () => toast.error("Failed to pause agent"),
      },
    );
  }

  function handleResume() {
    resumeAgent.mutate(uuid, {
      onSuccess: () => toast.success("Agent resumed"),
      onError: () => toast.error("Failed to resume agent"),
    });
  }

  function handleTerminate() {
    terminateAgent.mutate(uuid, {
      onSuccess: () => {
        toast.success("Agent terminated");
        setShowTerminateConfirm(false);
      },
      onError: () => {
        toast.error("Failed to terminate agent");
        setShowTerminateConfirm(false);
      },
    });
  }

  // --- Budget progress ---
  const budgetMonthly = agent.budget_monthly_cents ?? 0;
  const spentMonthly = agent.spent_monthly_cents ?? 0;
  const budgetProgressPercent = budgetMonthly > 0
    ? Math.min(100, (spentMonthly / budgetMonthly) * 100)
    : 0;
  const budgetProgressColor =
    budgetProgressPercent >= 90
      ? "bg-red-threat"
      : budgetProgressPercent >= 70
        ? "bg-amber"
        : "bg-teal";

  const agentStatus = agent.status ?? (agent.is_active ? "active" : "inactive");

  return (
    <AppLayout title="Agent Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/agents"
          title={agent.name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  agentStatus === "active"
                    ? "text-teal bg-teal/10 border-teal/30"
                    : agentStatus === "paused"
                      ? "text-amber bg-amber/10 border-amber/30"
                      : agentStatus === "terminated"
                        ? "text-red-threat bg-red-threat/10 border-red-threat/30"
                        : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {agentStatus}
              </Badge>
            </>
          }
          subtitle={
            agent.description ? (
              <p className="text-sm text-muted-foreground">{agent.description}</p>
            ) : undefined
          }
        />

        {/* Inline-editable status cards */}
        <DetailPageStatusCards
          items={[
            {
              label: "Status",
              icon: Shield,
              value: (
                <Select
                  value={agentStatus}
                  onValueChange={handleStatusChange}
                  disabled={agentStatus === "terminated"}
                >
                  <SelectTrigger
                    className={cn(
                      "h-7 w-full text-xs border",
                      agentStatus === "active"
                        ? "text-teal bg-teal/10 border-teal/30"
                        : agentStatus === "paused"
                          ? "text-amber bg-amber/10 border-amber/30"
                          : agentStatus === "terminated"
                            ? "text-red-threat bg-red-threat/10 border-red-threat/30"
                            : "text-dim bg-dim/10 border-dim/30",
                    )}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="paused">Paused</SelectItem>
                    <SelectItem value="terminated" className="text-red-threat">Terminated</SelectItem>
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

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-surface border border-border">
            <TabsTrigger value="configuration" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Settings className="h-3.5 w-3.5 mr-1" />
              Configuration
            </TabsTrigger>
            <TabsTrigger value="test" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Send className="h-3.5 w-3.5 mr-1" />
              Test
            </TabsTrigger>
            <TabsTrigger value="documentation" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Documentation
            </TabsTrigger>
            <TabsTrigger value="heartbeats" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Activity className="h-3.5 w-3.5 mr-1" />
              Heartbeats
            </TabsTrigger>
            <TabsTrigger value="cost" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <DollarSign className="h-3.5 w-3.5 mr-1" />
              Cost
            </TabsTrigger>
            <TabsTrigger value="work" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Layers className="h-3.5 w-3.5 mr-1" />
              Work
            </TabsTrigger>
            <TabsTrigger value="instructions" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Instructions
            </TabsTrigger>
            <TabsTrigger value="skills" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Wrench className="h-3.5 w-3.5 mr-1" />
              Skills
            </TabsTrigger>
            <TabsTrigger value="dashboard" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <LayoutDashboard className="h-3.5 w-3.5 mr-1" />
              Dashboard
            </TabsTrigger>
          </TabsList>
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
                    value={agent.endpoint_url ? <CopyableText text={agent.endpoint_url} mono className="text-xs" /> : <span className="text-dim text-xs">Not set</span>}
                  />
                  <DetailPageField
                    label="Auth Header"
                    value={agent.auth_header_name ? (
                      <span className="font-mono text-xs">{agent.auth_header_name}</span>
                    ) : (
                      <span className="text-dim">Not set</span>
                    )}
                  />
                  <DetailPageField label="Created" value={formatDate(agent.created_at)} />
                  <DetailPageField label="Updated" value={formatDate(agent.updated_at)} />
                </SidebarSection>
                <SidebarSection title="Triggers">
                  <DetailPageField
                    label="Sources"
                    value={
                      agent.trigger_on_sources.length > 0
                        ? agent.trigger_on_sources.join(", ")
                        : "All"
                    }
                  />
                  <DetailPageField
                    label="Severities"
                    value={
                      agent.trigger_on_severities.length > 0
                        ? agent.trigger_on_severities.join(", ")
                        : "All"
                    }
                  />
                </SidebarSection>
              </DetailPageSidebar>
            }
          >

            {/* Configuration Tab */}
            <TabsContent value="configuration" className="mt-4 space-y-6">

              {/* Agent Profile */}
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Shield className="h-3.5 w-3.5 text-teal" />
                      Agent Profile
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Execution mode */}
                  {agent.execution_mode && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Execution Mode</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs",
                          agent.execution_mode === "external"
                            ? "text-dim bg-dim/10 border-dim/30"
                            : agent.execution_mode === "claude_code"
                              ? "text-teal-light bg-teal-light/10 border-teal-light/30"
                              : "text-teal bg-teal/10 border-teal/30",
                        )}
                      >
                        {agent.execution_mode}
                      </Badge>
                    </div>
                  )}

                  {/* Agent type */}
                  {agent.agent_type && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Agent Type</span>
                      <Badge variant="outline" className="text-xs text-dim bg-dim/10 border-dim/30">
                        {agent.agent_type}
                      </Badge>
                    </div>
                  )}

                  {/* Role */}
                  {agent.role && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Role</span>
                      <span className="text-xs text-foreground">{agent.role}</span>
                    </div>
                  )}

                  {/* Status + lifecycle actions */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Lifecycle Status</span>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs",
                          agentStatus === "active"
                            ? "text-teal bg-teal/10 border-teal/30"
                            : agentStatus === "paused"
                              ? "text-amber bg-amber/10 border-amber/30"
                              : agentStatus === "terminated"
                                ? "text-red-threat bg-red-threat/10 border-red-threat/30"
                                : "text-dim bg-dim/10 border-dim/30",
                        )}
                      >
                        {agentStatus}
                      </Badge>
                      {agentStatus !== "terminated" && (
                        <div className="flex items-center gap-1">
                          {agentStatus === "paused" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleResume}
                              disabled={resumeAgent.isPending}
                              className="h-6 text-xs text-teal hover:text-teal px-2"
                            >
                              {resumeAgent.isPending ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Play className="h-3 w-3 mr-1" />
                              )}
                              Resume
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handlePause}
                              disabled={pauseAgent.isPending}
                              className="h-6 text-xs text-dim hover:text-amber px-2"
                            >
                              {pauseAgent.isPending ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Pause className="h-3 w-3 mr-1" />
                              )}
                              Pause
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowTerminateConfirm(true)}
                            className="h-6 text-xs text-dim hover:text-red-threat px-2"
                          >
                            <StopCircle className="h-3 w-3 mr-1" />
                            Terminate
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Budget & Limits */}
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <DollarSign className="h-3.5 w-3.5 text-dim" />
                      Budget &amp; Limits
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Monthly budget progress */}
                  {budgetMonthly > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">Monthly Budget</span>
                        <span className="text-xs text-foreground">
                          {formatCents(spentMonthly)} spent of {formatCents(budgetMonthly)}
                        </span>
                      </div>
                      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn("h-full transition-all duration-300 rounded-full", budgetProgressColor)}
                          style={{ width: `${budgetProgressPercent}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Max concurrent alerts */}
                  {(agent.max_concurrent_alerts ?? 0) > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Concurrent Alerts</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.max_concurrent_alerts}
                      </span>
                    </div>
                  )}

                  {/* Max cost per alert */}
                  {(agent.max_cost_per_alert_cents ?? 0) > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Cost per Alert</span>
                      <span className="text-xs text-foreground font-mono">
                        {formatCents(agent.max_cost_per_alert_cents!)}
                      </span>
                    </div>
                  )}

                  {/* Max investigation minutes */}
                  {(agent.max_investigation_minutes ?? 0) > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Investigation Time</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.max_investigation_minutes}m
                      </span>
                    </div>
                  )}

                  {/* Fallback if nothing to show */}
                  {budgetMonthly === 0 &&
                    !(agent.max_concurrent_alerts ?? 0) &&
                    !(agent.max_cost_per_alert_cents ?? 0) &&
                    !(agent.max_investigation_minutes ?? 0) && (
                      <p className="text-xs text-dim">No limits configured</p>
                    )}
                </CardContent>
              </Card>

              {/* Trigger Configuration */}
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
                <CardContent className="space-y-3">
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

                  {/* Advanced Rules */}
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
            </TabsContent>

            {/* Test Tab */}
            <TabsContent value="test" className="mt-4">
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
            </TabsContent>

            {/* Documentation Tab */}
            <TabsContent value="documentation" className="mt-4">
              <DocumentationEditor
                content={agent.documentation ?? ""}
                onSave={handleSaveDocumentation}
                isSaving={patchAgent.isPending}
              />
            </TabsContent>

            {/* Heartbeats Tab */}
            <TabsContent value="heartbeats" className="mt-4">
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Activity className="h-3.5 w-3.5 text-teal" />
                      Heartbeat Runs
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {heartbeatRuns.length === 0 ? (
                    <div className="py-12 text-center text-sm text-dim">No heartbeat runs</div>
                  ) : (
                    <ResizableTable storageKey="agent-heartbeats" columns={HEARTBEAT_COLUMNS}>
                      <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                          <ResizableTableHead columnKey="status" className="text-xs text-muted-foreground px-3">Status</ResizableTableHead>
                          <ResizableTableHead columnKey="started_at" className="text-xs text-muted-foreground px-3">Started</ResizableTableHead>
                          <ResizableTableHead columnKey="duration" className="text-xs text-muted-foreground px-3">Duration</ResizableTableHead>
                          <ResizableTableHead columnKey="alerts_processed" className="text-xs text-muted-foreground px-3">Alerts</ResizableTableHead>
                          <ResizableTableHead columnKey="actions_proposed" className="text-xs text-muted-foreground px-3">Actions</ResizableTableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {heartbeatRuns.map((run) => (
                          <>
                            <TableRow
                              key={run.uuid}
                              className="border-border cursor-pointer hover:bg-surface/50"
                              onClick={() =>
                                setExpandedHeartbeat(
                                  expandedHeartbeat === run.uuid ? null : run.uuid,
                                )
                              }
                            >
                              <TableCell className="px-3 py-2">
                                <Badge
                                  variant="outline"
                                  className={cn("text-xs", heartbeatStatusClass(run.status))}
                                >
                                  {run.status}
                                </Badge>
                              </TableCell>
                              <TableCell className="px-3 py-2 text-xs text-muted-foreground">
                                {run.started_at ? relativeTime(run.started_at) : "--"}
                              </TableCell>
                              <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                                {formatDuration(run.started_at, run.finished_at)}
                              </TableCell>
                              <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                                {run.alerts_processed}
                              </TableCell>
                              <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                                {run.actions_proposed}
                              </TableCell>
                            </TableRow>
                            {expandedHeartbeat === run.uuid && (
                              <TableRow key={`${run.uuid}-expanded`} className="border-border bg-surface/30">
                                <TableCell colSpan={5} className="px-3 py-3">
                                  {run.error && (
                                    <div className="mb-2 rounded-md bg-red-threat/5 border border-red-threat/20 p-2">
                                      <p className="text-xs text-red-threat font-mono">{run.error}</p>
                                    </div>
                                  )}
                                  {run.context_snapshot && (
                                    <pre className="text-xs font-mono text-muted-foreground bg-surface border border-border rounded-md p-2 overflow-x-auto max-h-48">
                                      {JSON.stringify(run.context_snapshot, null, 2)}
                                    </pre>
                                  )}
                                  {!run.error && !run.context_snapshot && (
                                    <p className="text-xs text-dim">No additional details</p>
                                  )}
                                </TableCell>
                              </TableRow>
                            )}
                          </>
                        ))}
                      </TableBody>
                    </ResizableTable>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Cost Tab */}
            <TabsContent value="cost" className="mt-4 space-y-4">
              {/* Summary */}
              <div className="grid grid-cols-1 gap-3">
                <Card className="bg-card border-border">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Total Cost (this period)</span>
                      <span className="text-lg font-mono font-semibold text-foreground">
                        {formatCents(totalCostCents)}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Table */}
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <DollarSign className="h-3.5 w-3.5 text-dim" />
                      Cost Events
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {costEvents.length === 0 ? (
                    <div className="py-12 text-center text-sm text-dim">No cost events</div>
                  ) : (
                    <ResizableTable storageKey="agent-cost-events" columns={COST_COLUMNS}>
                      <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                          <ResizableTableHead columnKey="provider" className="text-xs text-muted-foreground px-3">Provider</ResizableTableHead>
                          <ResizableTableHead columnKey="model" className="text-xs text-muted-foreground px-3">Model</ResizableTableHead>
                          <ResizableTableHead columnKey="input_tokens" className="text-xs text-muted-foreground px-3">Input Tokens</ResizableTableHead>
                          <ResizableTableHead columnKey="output_tokens" className="text-xs text-muted-foreground px-3">Output Tokens</ResizableTableHead>
                          <ResizableTableHead columnKey="cost" className="text-xs text-muted-foreground px-3">Cost</ResizableTableHead>
                          <ResizableTableHead columnKey="billing_type" className="text-xs text-muted-foreground px-3">Billing Type</ResizableTableHead>
                          <ResizableTableHead columnKey="occurred_at" className="text-xs text-muted-foreground px-3">When</ResizableTableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {costEvents.map((event) => (
                          <TableRow key={event.id} className="border-border hover:bg-surface/50">
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                              {event.provider}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-muted-foreground truncate">
                              {event.model}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                              {event.input_tokens.toLocaleString()}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                              {event.output_tokens.toLocaleString()}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                              {formatCents(event.cost_cents)}
                            </TableCell>
                            <TableCell className="px-3 py-2">
                              <Badge variant="outline" className="text-xs text-dim bg-dim/10 border-dim/30">
                                {event.billing_type}
                              </Badge>
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">
                              {relativeTime(event.occurred_at)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </ResizableTable>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Work Tab */}
            <TabsContent value="work" className="mt-4">
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Layers className="h-3.5 w-3.5 text-teal" />
                      Invocations
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {invocations.length === 0 ? (
                    <div className="py-12 text-center text-sm text-dim">No invocations</div>
                  ) : (
                    <ResizableTable storageKey="agent-invocations" columns={INVOCATION_COLUMNS}>
                      <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                          <ResizableTableHead columnKey="task_description" className="text-xs text-muted-foreground px-3">Task</ResizableTableHead>
                          <ResizableTableHead columnKey="status" className="text-xs text-muted-foreground px-3">Status</ResizableTableHead>
                          <ResizableTableHead columnKey="cost" className="text-xs text-muted-foreground px-3">Cost</ResizableTableHead>
                          <ResizableTableHead columnKey="started_at" className="text-xs text-muted-foreground px-3">Started</ResizableTableHead>
                          <ResizableTableHead columnKey="completed_at" className="text-xs text-muted-foreground px-3">Completed</ResizableTableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {invocations.map((inv) => (
                          <TableRow key={inv.uuid} className="border-border hover:bg-surface/50">
                            <TableCell className="px-3 py-2 text-xs text-foreground truncate">
                              {inv.task_description.length > 60
                                ? `${inv.task_description.slice(0, 60)}…`
                                : inv.task_description}
                            </TableCell>
                            <TableCell className="px-3 py-2">
                              <Badge
                                variant="outline"
                                className={cn("text-xs", invocationStatusClass(inv.status))}
                              >
                                {inv.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">
                              {formatCents(inv.cost_cents)}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">
                              {inv.started_at ? relativeTime(inv.started_at) : "--"}
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">
                              {inv.completed_at ? relativeTime(inv.completed_at) : "pending"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </ResizableTable>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
            {/* Instructions Tab */}
            <TabsContent value="instructions" className="mt-4">
              <div className="flex border border-border rounded-lg overflow-hidden bg-card" style={{ minHeight: "400px" }}>
                {/* Left panel — file list */}
                <div className="w-1/3 border-r border-border flex flex-col">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                    <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Files</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setShowNewFileInput(true); setNewFileName(""); }}
                      className="h-6 w-6 p-0 text-dim hover:text-teal"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </div>

                  {/* New file inline input */}
                  {showNewFileInput && (
                    <div className="px-3 py-2 border-b border-border space-y-1.5">
                      <Input
                        value={newFileName}
                        onChange={(e) => setNewFileName(e.target.value)}
                        placeholder="filename.md"
                        autoFocus
                        className="h-7 text-xs bg-surface border-border font-mono"
                        onKeyDown={(e) => {
                          if (e.key === "Escape") { setShowNewFileInput(false); setNewFileName(""); }
                        }}
                      />
                      <div className="flex gap-1.5">
                        <Button
                          size="sm"
                          disabled={!newFileName.trim() || patchAgent.isPending}
                          className="h-6 text-xs bg-teal text-white hover:bg-teal-dim flex-1"
                          onClick={() => {
                            const name = newFileName.trim();
                            if (!name) return;
                            const existing = agent.instruction_files ?? [];
                            const updated = [...existing, { name, content: "" }];
                            patchAgent.mutate(
                              { uuid, body: { instruction_files: updated } },
                              {
                                onSuccess: () => {
                                  toast.success("File created");
                                  setShowNewFileInput(false);
                                  setNewFileName("");
                                  setSelectedInstructionFile(name);
                                },
                                onError: () => toast.error("Failed to create file"),
                              },
                            );
                          }}
                        >
                          Create
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs text-dim flex-1"
                          onClick={() => { setShowNewFileInput(false); setNewFileName(""); }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* File list */}
                  <div className="flex-1 overflow-y-auto">
                    {(!agent.instruction_files || agent.instruction_files.length === 0) && !showNewFileInput ? (
                      <div className="py-12 text-center text-xs text-dim px-3">No instruction files yet.</div>
                    ) : (
                      (agent.instruction_files ?? []).map((file) => (
                        <div
                          key={file.name}
                          className={cn(
                            "group flex items-center justify-between px-3 py-2 cursor-pointer border-b border-border transition-colors",
                            selectedInstructionFile === file.name
                              ? "bg-teal/10"
                              : "hover:bg-surface/50",
                          )}
                          onClick={() => setSelectedInstructionFile(file.name)}
                        >
                          <span className="text-xs font-mono text-foreground truncate flex-1">{file.name}</span>
                          <button
                            className="h-5 w-5 p-0 text-dim opacity-0 group-hover:opacity-100 hover:text-red-threat transition-opacity ml-2 shrink-0"
                            onClick={(e) => {
                              e.stopPropagation();
                              const updated = (agent.instruction_files ?? []).filter((f) => f.name !== file.name);
                              patchAgent.mutate(
                                { uuid, body: { instruction_files: updated } },
                                {
                                  onSuccess: () => {
                                    toast.success("File removed");
                                    if (selectedInstructionFile === file.name) setSelectedInstructionFile(null);
                                  },
                                  onError: () => toast.error("Failed to remove file"),
                                },
                              );
                            }}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Right panel — file editor */}
                <div className="flex-1 flex flex-col">
                  {selectedInstructionFile ? (
                    <>
                      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
                        <span className="text-xs font-mono text-muted-foreground">{selectedInstructionFile}</span>
                      </div>
                      <div className="flex-1 flex flex-col items-center justify-center gap-2 p-6 text-center">
                        <FileText className="h-8 w-8 text-dim" />
                        <p className="text-sm text-dim">File API coming soon</p>
                        <p className="text-xs text-dim">
                          Direct file editing will be available once <span className="font-mono">GET/PUT /v1/agents/&#123;uuid&#125;/files/&#123;path&#125;</span> is deployed.
                        </p>
                        <Button
                          size="sm"
                          disabled
                          className="mt-2 bg-teal text-white hover:bg-teal-dim disabled:opacity-40 text-xs"
                        >
                          <Save className="h-3 w-3 mr-1" />
                          Save
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-sm text-dim">
                      Select a file to edit.
                    </div>
                  )}
                </div>
              </div>
            </TabsContent>

            {/* Skills Tab */}
            <TabsContent value="skills" className="mt-4">
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Wrench className="h-3.5 w-3.5 text-teal" />
                      Assigned Tools
                    </div>
                  </CardTitle>
                  <Button
                    size="sm"
                    onClick={() => setShowAddToolDialog(true)}
                    className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    Add Tool
                  </Button>
                </CardHeader>
                <CardContent>
                  {(() => {
                    const assignedIds = new Set(agent.tool_ids ?? []);
                    const assignedTools = allTools.filter((t) => assignedIds.has(t.id));

                    function tierBadgeClass(tier: string): string {
                      switch (tier) {
                        case "safe": return "text-teal bg-teal/10 border-teal/30";
                        case "managed": return "text-teal-light bg-teal-light/10 border-teal-light/30";
                        case "requires_approval": return "text-amber bg-amber/10 border-amber/30";
                        case "forbidden": return "text-red-threat bg-red-threat/10 border-red-threat/30";
                        default: return "text-dim bg-dim/10 border-dim/30";
                      }
                    }

                    if (assignedTools.length === 0) {
                      return (
                        <div className="py-12 text-center text-sm text-dim">
                          No tools assigned. Click &lsquo;Add Tool&rsquo; to get started.
                        </div>
                      );
                    }

                    return (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {assignedTools.map((tool) => (
                          <div
                            key={tool.id}
                            className="flex items-start gap-3 p-3 rounded-md border border-border bg-surface hover:border-teal/20 transition-colors"
                          >
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-medium text-foreground font-mono">{tool.display_name}</span>
                                <Badge
                                  variant="outline"
                                  className={cn("text-[11px]", tierBadgeClass(tool.tier))}
                                >
                                  {tool.tier.replace("_", " ")}
                                </Badge>
                              </div>
                              <p className="text-xs text-dim line-clamp-2">{tool.description}</p>
                            </div>
                            <button
                              className="text-dim hover:text-red-threat transition-colors shrink-0 mt-0.5"
                              onClick={() => {
                                const updated = (agent.tool_ids ?? []).filter((id) => id !== tool.id);
                                patchAgent.mutate(
                                  { uuid, body: { tool_ids: updated } },
                                  {
                                    onSuccess: () => toast.success("Tool removed"),
                                    onError: () => toast.error("Failed to remove tool"),
                                  },
                                );
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>

              {/* Add Tool Dialog */}
              <Dialog open={showAddToolDialog} onOpenChange={setShowAddToolDialog}>
                <DialogContent className="bg-card border-border max-w-lg">
                  <DialogHeader>
                    <DialogTitle>Add Tool</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                    {(() => {
                      const assignedIds = new Set(agent.tool_ids ?? []);
                      const available = allTools.filter((t) => !assignedIds.has(t.id) && t.is_active);

                      function tierBadgeClass(tier: string): string {
                        switch (tier) {
                          case "safe": return "text-teal bg-teal/10 border-teal/30";
                          case "managed": return "text-teal-light bg-teal-light/10 border-teal-light/30";
                          case "requires_approval": return "text-amber bg-amber/10 border-amber/30";
                          case "forbidden": return "text-red-threat bg-red-threat/10 border-red-threat/30";
                          default: return "text-dim bg-dim/10 border-dim/30";
                        }
                      }

                      if (available.length === 0) {
                        return <p className="text-sm text-dim text-center py-6">No available tools to add.</p>;
                      }
                      return available.map((tool) => (
                        <button
                          key={tool.id}
                          className="w-full flex items-start gap-3 p-3 rounded-md border border-border bg-surface hover:border-teal/30 transition-colors text-left"
                          onClick={() => {
                            const updated = [...(agent.tool_ids ?? []), tool.id];
                            patchAgent.mutate(
                              { uuid, body: { tool_ids: updated } },
                              {
                                onSuccess: () => {
                                  toast.success("Tool added");
                                  setShowAddToolDialog(false);
                                },
                                onError: () => toast.error("Failed to add tool"),
                              },
                            );
                          }}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-xs font-medium text-foreground font-mono">{tool.display_name}</span>
                              <Badge
                                variant="outline"
                                className={cn("text-[11px]", tierBadgeClass(tool.tier))}
                              >
                                {tool.tier.replace("_", " ")}
                              </Badge>
                            </div>
                            <p className="text-xs text-dim line-clamp-2">{tool.description}</p>
                          </div>
                        </button>
                      ));
                    })()}
                  </div>
                </DialogContent>
              </Dialog>
            </TabsContent>

            {/* Dashboard Tab */}
            <TabsContent value="dashboard" className="mt-4 space-y-4">
              {/* Stat cards row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1">Total Runs</div>
                    <div className="text-lg font-mono font-semibold text-foreground">
                      {heartbeatData?.meta?.total ?? 0}
                    </div>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1">Cost This Month</div>
                    <div className="text-lg font-mono font-semibold text-foreground">
                      {costSummaryData?.data
                        ? formatCents(costSummaryData.data.total_cost_cents)
                        : <span className="text-sm text-dim">—</span>}
                    </div>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1">Active Assignments</div>
                    <div className="text-sm text-dim mt-1">Data not available</div>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-dim mb-1">Avg Run Duration</div>
                    <div className="text-lg font-mono font-semibold text-foreground">
                      {(() => {
                        const completed = heartbeatRuns.filter((r) => r.started_at && r.finished_at);
                        if (completed.length === 0) return <span className="text-sm text-dim">—</span>;
                        const avgMs = completed.reduce((sum, r) => {
                          return sum + (new Date(r.finished_at!).getTime() - new Date(r.started_at!).getTime());
                        }, 0) / completed.length;
                        if (avgMs < 1000) return `${Math.round(avgMs)}ms`;
                        if (avgMs < 60000) return `${(avgMs / 1000).toFixed(1)}s`;
                        return `${Math.round(avgMs / 60000)}m`;
                      })()}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Row 2 — Last runs + Activity */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Last 5 runs */}
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <Activity className="h-3.5 w-3.5 text-teal" />
                        Recent Runs
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {heartbeatRuns.length === 0 ? (
                      <div className="py-8 text-center text-sm text-dim">No runs yet</div>
                    ) : (
                      <div className="divide-y divide-border">
                        {heartbeatRuns.slice(0, 5).map((run) => (
                          <div key={run.uuid} className="flex items-center justify-between px-4 py-2">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="outline"
                                className={cn("text-[11px]", heartbeatStatusClass(run.status))}
                              >
                                {run.status}
                              </Badge>
                              <span className="text-xs text-dim">
                                {run.started_at ? relativeTime(run.started_at) : "--"}
                              </span>
                            </div>
                            <span className="text-xs font-mono text-muted-foreground">
                              {formatDuration(run.started_at, run.finished_at)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Recent Activity */}
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <Clock className="h-3.5 w-3.5 text-dim" />
                        Recent Activity
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {activityError ? (
                      <div className="py-8 text-center text-sm text-dim">Activity feed coming soon</div>
                    ) : !activityData ? (
                      <div className="py-8 text-center text-sm text-dim">Loading...</div>
                    ) : activityData.data.length === 0 ? (
                      <div className="py-8 text-center text-sm text-dim">No activity</div>
                    ) : (
                      <div className="space-y-2">
                        {activityData.data.map((event) => (
                          <div key={event.uuid} className="flex items-start gap-2">
                            <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-teal shrink-0" />
                            <div>
                              <span className="text-xs text-foreground">{event.event_type.replace(/_/g, " ")}</span>
                              <span className="text-xs text-dim ml-2">{relativeTime(event.created_at)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </DetailPageLayout>
        </Tabs>
      </div>

      {/* Terminate confirm dialog */}
      <ConfirmDialog
        open={showTerminateConfirm}
        onOpenChange={setShowTerminateConfirm}
        title="Terminate Agent"
        description="This will permanently terminate the agent. It cannot be restarted. Are you sure?"
        confirmLabel="Terminate"
        variant="destructive"
        onConfirm={handleTerminate}
      />
    </AppLayout>
  );
}
