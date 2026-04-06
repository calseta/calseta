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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  useAgentHeartbeatRuns,
  useAgentCostEvents,
  useAgentInvocations,
  usePauseAgent,
  useResumeAgent,
  useTerminateAgent,
  usePostHeartbeat,
  useCreateIssue,
  useLLMIntegrations,
} from "@/hooks/use-api";
import type { HeartbeatRun, CostEvent, AgentInvocation } from "@/lib/types";
import { formatDate, relativeTime } from "@/lib/format";
import {
  Globe,
  Pencil,
  Save,
  X,
  Send,
  Loader2,
  Lock,
  Shield,
  Zap,
  FileText,
  Settings,
  Activity,
  DollarSign,
  Layers,
  Pause,
  Play,
  StopCircle,
  MoreHorizontal,
  Heart,
} from "lucide-react";

const ALL_SEVERITIES = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];
const ALL_SOURCES = ["sentinel", "elastic", "splunk", "generic"];

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
  const pauseAgent = usePauseAgent();
  const resumeAgent = useResumeAgent();
  const terminateAgent = useTerminateAgent();
  const postHeartbeat = usePostHeartbeat();
  const createIssue = useCreateIssue();
  const { data: llmData } = useLLMIntegrations();
  const llmIntegrations = llmData?.data ?? [];

  // Trigger editing state
  const [sourcesDraft, setSourcesDraft] = useState<string[] | null>(null);
  const [severitiesDraft, setSeveritiesDraft] = useState<string[] | null>(null);
  const [editingFilter, setEditingFilter] = useState(false);
  const [filterDraft, setFilterDraft] = useState<TargetingRules | null>(null);

  // Auth editing state
  const [editingAuth, setEditingAuth] = useState(false);
  const [authHeaderName, setAuthHeaderName] = useState("");
  const [authHeaderValue, setAuthHeaderValue] = useState("");

  // Inline config editing
  const [configEditMode, setConfigEditMode] = useState(false);
  const [configDraft, setConfigDraft] = useState({
    description: "",
    endpoint_url: "",
    system_prompt: "",
    methodology: "",
    llm_integration_uuid: "",
    max_concurrent_alerts: "",
    max_cost_per_alert_dollars: "",
    max_investigation_minutes: "",
  });

  // Terminate confirm
  const [showTerminateConfirm, setShowTerminateConfirm] = useState(false);

  // Selected run for split-pane
  const [selectedRunUuid, setSelectedRunUuid] = useState<string | null>(null);

  // Assign task modal
  const [assignTaskOpen, setAssignTaskOpen] = useState(false);
  const [taskDescription, setTaskDescription] = useState("");

  // Budget input
  const [budgetInput, setBudgetInput] = useState("");

  const agent = data?.data;

  const { data: heartbeatData } = useAgentHeartbeatRuns(uuid);
  const { data: costData } = useAgentCostEvents(uuid);
  const { data: invocationData } = useAgentInvocations(uuid);

  const heartbeatRuns: HeartbeatRun[] = heartbeatData?.data ?? [];
  const costEvents: CostEvent[] = costData?.data ?? [];
  const invocations: AgentInvocation[] = invocationData?.data ?? [];

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

  // --- Status toggle ---
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

  // --- Triggers ---
  const triggersDirty = sourcesDraft !== null || severitiesDraft !== null;

  function toggleSource(source: string) {
    const current = sourcesDraft ?? [...agent!.trigger_on_sources];
    const next = current.includes(source) ? current.filter((s) => s !== source) : [...current, source];
    setSourcesDraft(next);
  }

  function toggleSeverity(sev: string) {
    const current = severitiesDraft ?? [...agent!.trigger_on_severities];
    const next = current.includes(sev) ? current.filter((s) => s !== sev) : [...current, sev];
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
    body.auth_header_name = authHeaderName.trim() || null;
    if (authHeaderValue.trim()) body.auth_header_value = authHeaderValue.trim();
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

  // --- Inline config edit ---
  function startConfigEdit() {
    const a = agent!;
    setConfigDraft({
      description: a.description ?? "",
      endpoint_url: a.endpoint_url ?? "",
      system_prompt: a.system_prompt ?? "",
      methodology: a.methodology ?? "",
      llm_integration_uuid: "",
      max_concurrent_alerts: a.max_concurrent_alerts ? String(a.max_concurrent_alerts) : "",
      max_cost_per_alert_dollars: a.max_cost_per_alert_cents ? (a.max_cost_per_alert_cents / 100).toFixed(2) : "",
      max_investigation_minutes: a.max_investigation_minutes ? String(a.max_investigation_minutes) : "",
    });
    setConfigEditMode(true);
  }

  function handleSaveConfig() {
    const body: Record<string, unknown> = {};
    body.description = configDraft.description || null;
    const isManaged = agent!.execution_mode === "claude_code" || agent!.execution_mode === "managed";
    if (!isManaged) {
      body.endpoint_url = configDraft.endpoint_url || null;
    }
    if (isManaged) {
      body.system_prompt = configDraft.system_prompt || null;
      body.methodology = configDraft.methodology || null;
      if (configDraft.llm_integration_uuid) body.llm_integration_uuid = configDraft.llm_integration_uuid;
    }
    body.max_concurrent_alerts = configDraft.max_concurrent_alerts ? Number(configDraft.max_concurrent_alerts) : null;
    body.max_cost_per_alert_cents = configDraft.max_cost_per_alert_dollars
      ? Math.round(parseFloat(configDraft.max_cost_per_alert_dollars) * 100)
      : null;
    body.max_investigation_minutes = configDraft.max_investigation_minutes
      ? Number(configDraft.max_investigation_minutes)
      : null;
    patchAgent.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Configuration saved");
          setConfigEditMode(false);
        },
        onError: () => toast.error("Failed to save configuration"),
      },
    );
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

  // --- Run Heartbeat ---
  function handleRunHeartbeat() {
    postHeartbeat.mutate(uuid, {
      onSuccess: () => toast.success("Heartbeat triggered"),
      onError: () => toast.error("Failed to trigger heartbeat"),
    });
  }

  // --- Assign Task ---
  function handleAssignTask() {
    if (!taskDescription.trim()) return;
    createIssue.mutate(
      { title: taskDescription.trim(), preferred_agent_id: uuid },
      {
        onSuccess: () => {
          toast.success("Task assigned");
          setAssignTaskOpen(false);
          setTaskDescription("");
        },
        onError: () => toast.error("Failed to assign task"),
      },
    );
  }

  // --- Set monthly budget ---
  function handleSetBudget() {
    const val = parseFloat(budgetInput);
    if (isNaN(val) || val < 0) {
      toast.error("Enter a valid dollar amount");
      return;
    }
    patchAgent.mutate(
      { uuid, body: { budget_monthly_cents: Math.round(val * 100) } },
      {
        onSuccess: () => {
          toast.success("Budget updated");
          setBudgetInput("");
        },
        onError: () => toast.error("Failed to update budget"),
      },
    );
  }

  // --- Budget progress ---
  const budgetMonthly = agent.budget_monthly_cents ?? 0;
  const spentMonthly = agent.spent_monthly_cents ?? 0;
  const budgetProgressPercent = budgetMonthly > 0 ? Math.min(100, (spentMonthly / budgetMonthly) * 100) : 0;
  const budgetProgressColor =
    budgetProgressPercent >= 100
      ? "bg-red-threat"
      : budgetProgressPercent >= 80
        ? "bg-amber"
        : "bg-teal";

  const agentStatus = agent.status ?? (agent.is_active ? "active" : "inactive");
  const isManaged = agent.execution_mode === "claude_code" || agent.execution_mode === "managed";
  const selectedRun = selectedRunUuid ? heartbeatRuns.find((r) => r.uuid === selectedRunUuid) : null;

  return (
    <AppLayout title="Agent Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/agents"
          title={agent.name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
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
          }
          subtitle={
            agent.description ? (
              <p className="text-sm text-muted-foreground">{agent.description}</p>
            ) : undefined
          }
          actions={
            agentStatus !== "terminated" ? (
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRunHeartbeat}
                  disabled={postHeartbeat.isPending}
                  className="h-8 text-xs border-border text-dim hover:text-foreground"
                >
                  {postHeartbeat.isPending ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <Heart className="h-3 w-3 mr-1" />
                  )}
                  Run Heartbeat
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAssignTaskOpen(true)}
                  className="h-8 text-xs border-border text-dim hover:text-foreground"
                >
                  <Send className="h-3 w-3 mr-1" />
                  Assign Task
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-dim hover:text-foreground">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="bg-card border-border">
                    {agentStatus === "paused" ? (
                      <DropdownMenuItem onClick={handleResume} className="text-sm cursor-pointer">
                        <Play className="h-3.5 w-3.5 mr-2" />
                        Resume Agent
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onClick={handlePause} className="text-sm cursor-pointer">
                        <Pause className="h-3.5 w-3.5 mr-2" />
                        Pause Agent
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator className="bg-border" />
                    <DropdownMenuItem
                      onClick={() => setShowTerminateConfirm(true)}
                      className="text-sm text-red-threat cursor-pointer focus:text-red-threat focus:bg-red-threat/10"
                    >
                      <StopCircle className="h-3.5 w-3.5 mr-2" />
                      Terminate Agent
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ) : undefined
          }
        />

        {/* Status cards */}
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
              value: agent.endpoint_url ? (
                <span className="font-mono text-xs truncate">{agent.endpoint_url}</span>
              ) : (
                <span className="text-dim text-xs">Not set</span>
              ),
            },
            {
              label: "Monthly Budget",
              icon: DollarSign,
              value: budgetMonthly > 0 ? (
                <span className="text-xs text-foreground font-mono">
                  {formatCents(spentMonthly)} / {formatCents(budgetMonthly)}
                </span>
              ) : (
                <span className="text-xs text-dim">No budget</span>
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
            <TabsTrigger value="documentation" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Documentation
            </TabsTrigger>
            <TabsTrigger value="runs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Activity className="h-3.5 w-3.5 mr-1" />
              Runs
            </TabsTrigger>
            <TabsTrigger value="cost" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <DollarSign className="h-3.5 w-3.5 mr-1" />
              Cost
            </TabsTrigger>
            <TabsTrigger value="assignments" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Layers className="h-3.5 w-3.5 mr-1" />
              Assignments
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
                    value={
                      agent.endpoint_url
                        ? <CopyableText text={agent.endpoint_url} mono className="text-xs" />
                        : <span className="text-dim text-xs">Not set</span>
                    }
                  />
                  <DetailPageField
                    label="Auth Header"
                    value={
                      agent.auth_header_name
                        ? <span className="font-mono text-xs">{agent.auth_header_name}</span>
                        : <span className="text-dim">Not set</span>
                    }
                  />
                  <DetailPageField label="Created" value={formatDate(agent.created_at)} />
                  <DetailPageField label="Updated" value={formatDate(agent.updated_at)} />
                </SidebarSection>
                <SidebarSection title="Triggers">
                  <DetailPageField
                    label="Sources"
                    value={agent.trigger_on_sources.length > 0 ? agent.trigger_on_sources.join(", ") : "All"}
                  />
                  <DetailPageField
                    label="Severities"
                    value={agent.trigger_on_severities.length > 0 ? agent.trigger_on_severities.join(", ") : "All"}
                  />
                </SidebarSection>
              </DetailPageSidebar>
            }
          >
            {/* Configuration Tab */}
            <TabsContent value="configuration" className="mt-4 space-y-6">

              {/* Agent Configuration (inline editable) */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Settings className="h-3.5 w-3.5 text-teal" />
                      Agent Configuration
                    </div>
                  </CardTitle>
                  {!configEditMode ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={startConfigEdit}
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
                        onClick={() => setConfigEditMode(false)}
                        className="h-7 text-xs text-dim"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveConfig}
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
                  {/* Description */}
                  {configEditMode ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Description</Label>
                      <Textarea
                        value={configDraft.description}
                        onChange={(e) => setConfigDraft({ ...configDraft, description: e.target.value })}
                        placeholder="Describe this agent..."
                        className="bg-surface border-border text-sm min-h-16 resize-none"
                        rows={3}
                      />
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs text-muted-foreground shrink-0">Description</span>
                      <span className="text-xs text-foreground text-right max-w-xs">
                        {agent.description ?? <span className="text-dim">Not set</span>}
                      </span>
                    </div>
                  )}

                  {/* Endpoint URL (external only) */}
                  {!isManaged && (
                    configEditMode ? (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Endpoint URL</Label>
                        <Input
                          value={configDraft.endpoint_url}
                          onChange={(e) => setConfigDraft({ ...configDraft, endpoint_url: e.target.value })}
                          placeholder="https://..."
                          className="bg-surface border-border text-sm font-mono"
                        />
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">Endpoint URL</span>
                        <span className="text-xs text-foreground font-mono truncate max-w-xs">
                          {agent.endpoint_url ?? <span className="text-dim">Not set</span>}
                        </span>
                      </div>
                    )
                  )}

                  {/* System Prompt (managed only) */}
                  {isManaged && (
                    configEditMode ? (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">System Prompt</Label>
                        <Textarea
                          value={configDraft.system_prompt}
                          onChange={(e) => setConfigDraft({ ...configDraft, system_prompt: e.target.value })}
                          placeholder="System prompt..."
                          className="bg-surface border-border text-sm min-h-20 resize-none font-mono text-xs"
                          rows={4}
                        />
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-xs text-muted-foreground shrink-0">System Prompt</span>
                        <span className="text-xs text-foreground text-right max-w-xs">
                          {agent.system_prompt
                            ? `${agent.system_prompt.slice(0, 80)}${agent.system_prompt.length > 80 ? "…" : ""}`
                            : <span className="text-dim">Not set</span>}
                        </span>
                      </div>
                    )
                  )}

                  {/* Methodology (managed only) */}
                  {isManaged && (
                    configEditMode ? (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Methodology</Label>
                        <Textarea
                          value={configDraft.methodology}
                          onChange={(e) => setConfigDraft({ ...configDraft, methodology: e.target.value })}
                          placeholder="Investigation methodology..."
                          className="bg-surface border-border text-sm min-h-16 resize-none"
                          rows={3}
                        />
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-xs text-muted-foreground shrink-0">Methodology</span>
                        <span className="text-xs text-foreground text-right max-w-xs truncate">
                          {agent.methodology ?? <span className="text-dim">Not set</span>}
                        </span>
                      </div>
                    )
                  )}

                  {/* LLM Integration (managed only) */}
                  {isManaged && (
                    configEditMode ? (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">LLM Integration</Label>
                        <Select
                          value={configDraft.llm_integration_uuid}
                          onValueChange={(v) => setConfigDraft({ ...configDraft, llm_integration_uuid: v })}
                        >
                          <SelectTrigger className="bg-surface border-border text-sm">
                            <SelectValue placeholder="Select integration..." />
                          </SelectTrigger>
                          <SelectContent className="bg-card border-border">
                            <SelectItem value="">None</SelectItem>
                            {llmIntegrations.map((llm) => (
                              <SelectItem key={llm.uuid} value={llm.uuid}>
                                {llm.name} ({llm.provider}/{llm.model})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">LLM Integration</span>
                        <span className="text-xs text-foreground">
                          {agent.llm_integration_id
                            ? (llmIntegrations.find((l: any) => l.id === agent.llm_integration_id)?.name ?? `ID: ${agent.llm_integration_id}`)
                            : <span className="text-dim">Not set</span>}
                        </span>
                      </div>
                    )
                  )}

                  <div className="border-t border-border" />

                  {/* Max Concurrent Alerts */}
                  {configEditMode ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Max Concurrent Alerts</Label>
                      <Input
                        type="number"
                        min="0"
                        value={configDraft.max_concurrent_alerts}
                        onChange={(e) => setConfigDraft({ ...configDraft, max_concurrent_alerts: e.target.value })}
                        placeholder="No limit"
                        className="bg-surface border-border text-sm"
                      />
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Concurrent Alerts</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.max_concurrent_alerts ?? <span className="text-dim">No limit</span>}
                      </span>
                    </div>
                  )}

                  {/* Max Cost per Alert */}
                  {configEditMode ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Max Cost per Alert ($)</Label>
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={configDraft.max_cost_per_alert_dollars}
                        onChange={(e) => setConfigDraft({ ...configDraft, max_cost_per_alert_dollars: e.target.value })}
                        placeholder="No limit"
                        className="bg-surface border-border text-sm"
                      />
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Cost per Alert</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.max_cost_per_alert_cents ? formatCents(agent.max_cost_per_alert_cents) : <span className="text-dim">No limit</span>}
                      </span>
                    </div>
                  )}

                  {/* Max Investigation Minutes */}
                  {configEditMode ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Max Investigation Minutes</Label>
                      <Input
                        type="number"
                        min="0"
                        value={configDraft.max_investigation_minutes}
                        onChange={(e) => setConfigDraft({ ...configDraft, max_investigation_minutes: e.target.value })}
                        placeholder="No limit"
                        className="bg-surface border-border text-sm"
                      />
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Max Investigation Time</span>
                      <span className="text-xs text-foreground font-mono">
                        {agent.max_investigation_minutes ? `${agent.max_investigation_minutes}m` : <span className="text-dim">No limit</span>}
                      </span>
                    </div>
                  )}

                  <div className="border-t border-border" />

                  {/* Run Policy */}
                  <div>
                    <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Run Policy</span>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Heartbeat Interval</span>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="flex items-center gap-1.5 opacity-50 cursor-not-allowed">
                              <Input
                                disabled
                                placeholder="—"
                                className="h-7 w-16 bg-surface border-border text-xs"
                              />
                              <Select disabled>
                                <SelectTrigger className="h-7 w-24 bg-surface border-border text-xs">
                                  <SelectValue placeholder="minutes" />
                                </SelectTrigger>
                                <SelectContent className="bg-card border-border">
                                  <SelectItem value="minutes">minutes</SelectItem>
                                  <SelectItem value="hours">hours</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="bg-card border-border text-xs">
                            Coming soon
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </div>
                </CardContent>
              </Card>

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
                  {agent.agent_type && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Agent Type</span>
                      <Badge variant="outline" className="text-xs text-dim bg-dim/10 border-dim/30">
                        {agent.agent_type}
                      </Badge>
                    </div>
                  )}
                  {agent.role && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Role</span>
                      <span className="text-xs text-foreground">{agent.role}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Lifecycle Status</span>
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
                  </div>
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
                      <Button variant="ghost" size="sm" onClick={handleCancelTriggers} className="h-7 text-xs text-dim">
                        <X className="h-3 w-3 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveTriggers}
                        disabled={patchAgent.isPending}
                        className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                      >
                        {patchAgent.isPending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
                        Save
                      </Button>
                    </div>
                  )}
                </CardHeader>
                <CardContent className="space-y-3">
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
                              selected ? "bg-teal/15 border-teal/40 text-teal-light" : "bg-surface border-border text-dim hover:border-teal/30",
                            )}
                          >
                            {source}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="border-t border-border" />
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
                              selected ? "bg-teal/15 border-teal/40 text-teal-light" : "bg-surface border-border text-dim hover:border-teal/30",
                            )}
                          >
                            {sev}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="border-t border-border" />
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Advanced Rules</span>
                        <p className="text-[11px] text-dim mt-0.5">Match_any (OR) and match_all (AND) conditions against alert fields.</p>
                      </div>
                      {!editingFilter ? (
                        <Button variant="ghost" size="sm" onClick={startEditingFilter} className="h-7 text-xs text-dim hover:text-teal">
                          <Pencil className="h-3 w-3 mr-1" />
                          Edit
                        </Button>
                      ) : (
                        <div className="flex gap-1.5">
                          <Button variant="ghost" size="sm" onClick={() => setEditingFilter(false)} className="h-7 text-xs text-dim">
                            <X className="h-3 w-3 mr-1" />
                            Cancel
                          </Button>
                          <Button size="sm" onClick={handleSaveFilter} disabled={patchAgent.isPending} className="h-7 text-xs bg-teal text-white hover:bg-teal-dim">
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
              {isManaged ? (
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <Lock className="h-3.5 w-3.5 text-dim" />
                        Authentication
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-dim">Managed by adapter config.</p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="bg-card border-border">
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <Lock className="h-3.5 w-3.5 text-dim" />
                        Authentication
                      </div>
                    </CardTitle>
                    {!editingAuth ? (
                      <Button variant="ghost" size="sm" onClick={startEditingAuth} className="h-7 text-xs text-dim hover:text-teal">
                        <Pencil className="h-3 w-3 mr-1" />
                        Edit
                      </Button>
                    ) : (
                      <div className="flex gap-1.5">
                        <Button variant="ghost" size="sm" onClick={() => setEditingAuth(false)} className="h-7 text-xs text-dim">
                          <X className="h-3 w-3 mr-1" />
                          Cancel
                        </Button>
                        <Button size="sm" onClick={handleSaveAuth} disabled={patchAgent.isPending} className="h-7 text-xs bg-teal text-white hover:bg-teal-dim">
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
                          <p className="text-[11px] text-dim mt-1">The value is encrypted at rest. Leave empty to keep the existing value.</p>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">Header Name</span>
                          <span className="text-xs text-foreground font-mono">{agent.auth_header_name || "Not set"}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">Header Value</span>
                          <Badge
                            variant="outline"
                            className={cn("text-[11px]", agent.auth_header_name ? "text-teal border-teal/30" : "text-dim border-border")}
                          >
                            {agent.auth_header_name ? "configured" : "not set"}
                          </Badge>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            {/* Documentation Tab */}
            <TabsContent value="documentation" className="mt-4">
              <DocumentationEditor
                content={agent.documentation ?? ""}
                onSave={handleSaveDocumentation}
                isSaving={patchAgent.isPending}
              />
            </TabsContent>

            {/* Runs Tab — split pane */}
            <TabsContent value="runs" className="mt-4">
              <Card className="bg-card border-border overflow-hidden">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Activity className="h-3.5 w-3.5 text-teal" />
                      Runs
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {heartbeatRuns.length === 0 ? (
                    <div className="py-12 text-center text-sm text-dim">No runs yet.</div>
                  ) : (
                    <div className="flex h-[480px]">
                      {/* Left: run list */}
                      <div className="w-[35%] border-r border-border overflow-y-auto shrink-0">
                        {heartbeatRuns.map((run) => {
                          const isSelected = selectedRunUuid === run.uuid;
                          return (
                            <button
                              key={run.uuid}
                              type="button"
                              onClick={() => setSelectedRunUuid(isSelected ? null : run.uuid)}
                              className={cn(
                                "w-full text-left px-3 py-2.5 border-b border-border transition-colors",
                                isSelected ? "bg-teal/10" : "hover:bg-surface/50",
                              )}
                            >
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="font-mono text-[11px] text-dim">#{run.uuid.slice(-6)}</span>
                                <Badge
                                  variant="outline"
                                  className={cn("text-[10px] px-1.5 py-0", heartbeatStatusClass(run.status))}
                                >
                                  {run.status}
                                </Badge>
                              </div>
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-[11px] text-muted-foreground">
                                  {run.started_at ? relativeTime(run.started_at) : "—"}
                                </span>
                                <span className="font-mono text-[11px] text-dim">
                                  {formatDuration(run.started_at, run.finished_at)}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div>

                      {/* Right: run detail */}
                      <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {!selectedRun ? (
                          <div className="h-full flex items-center justify-center">
                            <p className="text-sm text-dim">Select a run to view details.</p>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center justify-between">
                              <Badge
                                variant="outline"
                                className={cn("text-xs", heartbeatStatusClass(selectedRun.status))}
                              >
                                {selectedRun.status}
                              </Badge>
                              <span className="font-mono text-[11px] text-dim">#{selectedRun.uuid.slice(-6)}</span>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <p className="text-[11px] text-muted-foreground mb-0.5">Started</p>
                                <p className="text-xs text-foreground">{selectedRun.started_at ? formatDate(selectedRun.started_at) : "—"}</p>
                              </div>
                              <div>
                                <p className="text-[11px] text-muted-foreground mb-0.5">Completed</p>
                                <p className="text-xs text-foreground">{selectedRun.finished_at ? formatDate(selectedRun.finished_at) : "—"}</p>
                              </div>
                              <div>
                                <p className="text-[11px] text-muted-foreground mb-0.5">Duration</p>
                                <p className="text-xs text-foreground font-mono">{formatDuration(selectedRun.started_at, selectedRun.finished_at)}</p>
                              </div>
                              <div>
                                <p className="text-[11px] text-muted-foreground mb-0.5">Alerts / Actions</p>
                                <p className="text-xs text-foreground font-mono">{selectedRun.alerts_processed} / {selectedRun.actions_proposed}</p>
                              </div>
                            </div>
                            {selectedRun.error && (
                              <div className="rounded-md bg-red-threat/5 border border-red-threat/20 p-3">
                                <p className="text-xs text-red-threat font-mono">{selectedRun.error}</p>
                              </div>
                            )}
                            {selectedRun.context_snapshot && (
                              <div>
                                <p className="text-[11px] text-muted-foreground mb-1.5">Log Output</p>
                                <pre className="text-xs font-mono text-white bg-zinc-950 border border-border rounded-md p-3 overflow-y-auto max-h-96 overflow-x-auto leading-relaxed">
                                  {JSON.stringify(selectedRun.context_snapshot, null, 2)}
                                </pre>
                              </div>
                            )}
                            {!selectedRun.error && !selectedRun.context_snapshot && (
                              <p className="text-xs text-dim">No additional details.</p>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Cost Tab */}
            <TabsContent value="cost" className="mt-4 space-y-4">
              {/* Budget Controls */}
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <DollarSign className="h-3.5 w-3.5 text-teal" />
                      Monthly Budget
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {budgetMonthly > 0 ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">
                          Spent: <span className="text-foreground font-mono">{formatCents(spentMonthly)}</span>
                          {" / "}
                          <span className="text-foreground font-mono">{formatCents(budgetMonthly)}</span>
                        </span>
                        <span className="text-xs text-dim font-mono">{budgetProgressPercent.toFixed(0)}% used</span>
                      </div>
                      <div className="relative h-2 w-full overflow-hidden rounded-full bg-surface border border-border">
                        <div
                          className={cn("h-full transition-all duration-300 rounded-full", budgetProgressColor)}
                          style={{ width: `${budgetProgressPercent}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-dim">No budget set.</p>
                  )}
                  <div className="flex items-center gap-2">
                    <Label className="text-xs text-muted-foreground shrink-0">Set monthly budget ($)</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={budgetInput}
                      onChange={(e) => setBudgetInput(e.target.value)}
                      placeholder="0.00"
                      className="h-8 bg-surface border-border text-sm w-28"
                    />
                    <Button
                      size="sm"
                      onClick={handleSetBudget}
                      disabled={patchAgent.isPending || !budgetInput}
                      className="h-8 text-xs bg-teal text-white hover:bg-teal-dim"
                    >
                      {patchAgent.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Set Budget"}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Summary */}
              <Card className="bg-card border-border">
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Total Cost (this period)</span>
                    <span className="text-lg font-mono font-semibold text-foreground">{formatCents(totalCostCents)}</span>
                  </div>
                </CardContent>
              </Card>

              {/* Cost Events Table */}
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
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">{event.provider}</TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-muted-foreground truncate">{event.model}</TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">{event.input_tokens.toLocaleString()}</TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">{event.output_tokens.toLocaleString()}</TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">{formatCents(event.cost_cents)}</TableCell>
                            <TableCell className="px-3 py-2">
                              <Badge variant="outline" className="text-xs text-dim bg-dim/10 border-dim/30">{event.billing_type}</Badge>
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">{relativeTime(event.occurred_at)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </ResizableTable>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Assignments Tab */}
            <TabsContent value="assignments" className="mt-4">
              <Card className="bg-card border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <Layers className="h-3.5 w-3.5 text-teal" />
                      Assignments
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
                              {inv.task_description.length > 60 ? `${inv.task_description.slice(0, 60)}…` : inv.task_description}
                            </TableCell>
                            <TableCell className="px-3 py-2">
                              <Badge variant="outline" className={cn("text-xs", invocationStatusClass(inv.status))}>
                                {inv.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="px-3 py-2 text-xs font-mono text-foreground">{formatCents(inv.cost_cents)}</TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">{inv.started_at ? relativeTime(inv.started_at) : "--"}</TableCell>
                            <TableCell className="px-3 py-2 text-xs text-muted-foreground">{inv.completed_at ? relativeTime(inv.completed_at) : "pending"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </ResizableTable>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </DetailPageLayout>
        </Tabs>
      </div>

      {/* Terminate confirm dialog */}
      <ConfirmDialog
        open={showTerminateConfirm}
        onOpenChange={setShowTerminateConfirm}
        title="Terminate Agent"
        description="This will permanently terminate the agent. This cannot be undone."
        confirmLabel="Terminate"
        variant="destructive"
        onConfirm={handleTerminate}
      />

      {/* Assign Task modal */}
      <Dialog open={assignTaskOpen} onOpenChange={setAssignTaskOpen}>
        <DialogContent className="bg-card border-border max-w-lg">
          <DialogHeader>
            <DialogTitle>Assign Task</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Task description</Label>
              <Textarea
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                placeholder="Describe the task for this agent..."
                className="bg-surface border-border text-sm min-h-24"
                rows={4}
              />
            </div>
            <Button
              onClick={handleAssignTask}
              disabled={createIssue.isPending || !taskDescription.trim()}
              className="w-full bg-teal text-white hover:bg-teal-dim"
            >
              {createIssue.isPending ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5 mr-1" />
              )}
              Submit
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
