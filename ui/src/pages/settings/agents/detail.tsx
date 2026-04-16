import { useState, useRef, useEffect, useCallback } from "react";
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
import { MarkdownPreview } from "@/components/markdown-preview";
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
  useAgentCostSummary,
  useTools,
  useAgentFiles,
  useSaveAgentFile,
  useAgentSkills,
  useSkills,
  useSyncAgentSkills,
  useDeleteAgent,
  useCancelRun,
} from "@/hooks/use-api";
import { RunTranscriptPanel } from "@/components/run-transcript/run-transcript-panel";
import type { HeartbeatRun, CostEvent, AgentInvocation, AgentTool, Skill } from "@/lib/types";
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
  Trash2,
  Heart,
  BookOpen,
  Wrench,
  LayoutDashboard,
  Plus,
  Info,
  TrendingUp,
  CheckCircle2,
  Clock,
  Bold,
  Italic,
  Heading2,
  List,
  Code2,
  Link2,
  Eye,
  XCircle,
} from "lucide-react";

const ALL_SEVERITIES = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];
const ALL_SOURCES = ["sentinel", "elastic", "splunk", "generic"];

function heartbeatStatusClass(status: string): string {
  switch (status) {
    case "succeeded": return "text-teal bg-teal/10 border-teal/30";
    case "failed": return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "running": return "text-teal bg-teal/10 border-teal/30 animate-pulse";
    case "cancelled": return "text-[#9CA3AF] bg-[#57635F]/30 border-[#57635F]/50";
    case "timed_out": return "text-amber bg-amber/10 border-amber/30";
    case "queued": return "text-muted-foreground bg-muted/50 border-muted";
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

function InlineTitle({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);

  function commit() {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) onSave(trimmed);
    else setDraft(value);
  }

  function cancel() {
    setEditing(false);
    setDraft(value);
  }

  if (editing) {
    return (
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
          if (e.key === "Escape") { e.preventDefault(); cancel(); }
        }}
        autoFocus
        className="text-xl font-heading font-extrabold tracking-tight text-foreground bg-transparent border-b border-teal outline-none w-full"
      />
    );
  }

  return (
    <h2
      className="text-xl font-heading font-extrabold tracking-tight text-foreground cursor-pointer rounded px-1 -mx-1 hover:bg-muted/40 transition-colors"
      onClick={() => { setDraft(value); setEditing(true); }}
    >
      {value}
    </h2>
  );
}

export function AgentDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { tab: activeTab } = useSearch({ from: "/agents/$uuid" });
  const navigate = useNavigate({ from: "/agents/$uuid" });
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
    llm_integration_id: "__none__",
    max_concurrent_alerts: "",
    max_cost_per_alert_dollars: "",
    max_investigation_minutes: "",
  });

  // Terminate confirm
  const [showTerminateConfirm, setShowTerminateConfirm] = useState(false);

  // Delete confirm
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const deleteAgent = useDeleteAgent();

  // Selected run for split-pane
  const [selectedRunUuid, setSelectedRunUuid] = useState<string | null>(null);

  // Transcript panel (slide-out sheet)
  const [transcriptRunUuid, setTranscriptRunUuid] = useState<string | null>(null);
  const [showCancelRunConfirm, setShowCancelRunConfirm] = useState<string | null>(null);
  const cancelRun = useCancelRun();

  // Assign task modal
  const [assignTaskOpen, setAssignTaskOpen] = useState(false);
  const [taskDescription, setTaskDescription] = useState("");

  // Budget input
  const [budgetInput, setBudgetInput] = useState("");

  // Instructions tab state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContentDraft, setFileContentDraft] = useState<string>("");
  const [newFileName, setNewFileName] = useState<string>("");
  const [showNewFileInput, setShowNewFileInput] = useState(false);
  // Tracks files created via + but not yet returned by the API (pre-first-save)
  const [pendingCreates, setPendingCreates] = useState<string[]>([]);
  const [fileEditorMode, setFileEditorMode] = useState<"write" | "preview">("write");
  const fileTextareaRef = useRef<HTMLTextAreaElement>(null);
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveAgentFile = useSaveAgentFile();

  const doSaveFile = useCallback((path: string, content: string) => {
    saveAgentFile.mutate(
      { agentUuid: uuid, path, content },
      {
        onSuccess: () => {
          setPendingCreates((prev) => prev.filter((n) => n !== path));
          toast.success("File saved");
        },
        onError: () => toast.error("Failed to save file"),
      },
    );
  }, [saveAgentFile, uuid]);

  // Autosave: fire 1.5 s after last keystroke when a file is open
  useEffect(() => {
    if (!selectedFile) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      doSaveFile(selectedFile, fileContentDraft);
    }, 1500);
    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileContentDraft]);

  function wrapFileSelection(before: string, after: string) {
    const el = fileTextareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = fileContentDraft.slice(start, end);
    const next = fileContentDraft.slice(0, start) + before + selected + after + fileContentDraft.slice(end);
    setFileContentDraft(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + before.length, start + before.length + selected.length);
    });
  }

  function prependFileLines(prefix: string) {
    const el = fileTextareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const lineStart = fileContentDraft.slice(0, start).lastIndexOf("\n") + 1;
    const lines = fileContentDraft.slice(lineStart, end === start ? end : end).split("\n");
    const next = fileContentDraft.slice(0, lineStart) + lines.map((l) => prefix + l).join("\n") + fileContentDraft.slice(end === start ? end : end);
    setFileContentDraft(next);
    requestAnimationFrame(() => el.focus());
  }

  function createNewFile(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    setPendingCreates((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
    setSelectedFile(trimmed);
    setFileContentDraft("");
    setFileEditorMode("write");
    setShowNewFileInput(false);
    setNewFileName("");
  }

  const agent = data?.data;

  const { data: heartbeatData } = useAgentHeartbeatRuns(uuid);
  const { data: costData } = useAgentCostEvents(uuid);
  const { data: invocationData } = useAgentInvocations(uuid);
  const { data: costSummaryData } = useAgentCostSummary(uuid);
  const { data: toolsData } = useTools();
  const { data: agentFilesData, isLoading: filesLoading } = useAgentFiles(uuid);
  const { data: agentSkillsData } = useAgentSkills(uuid);
  const { data: allSkillsData } = useSkills();
  const syncAgentSkills = useSyncAgentSkills();

  const heartbeatRuns: HeartbeatRun[] = heartbeatData?.data ?? [];
  const costEvents: CostEvent[] = costData?.data ?? [];
  const invocations: AgentInvocation[] = invocationData?.data ?? [];

  const totalCostCents = costEvents.reduce((sum, e) => sum + e.cost_cents, 0);

  // Instructions tab derived data
  const agentFiles: Array<{ name: string; content: string }> = agentFilesData?.data ?? agent?.instruction_files ?? [];
  const allTools: AgentTool[] = toolsData?.data ?? [];
  const assignedToolIds = new Set(agent?.tool_ids ?? []);
  const assignedTools = allTools.filter((t) => assignedToolIds.has(t.id));
  const costSummary = costSummaryData?.data ?? null;

  // Skills
  const allSkills: Skill[] = allSkillsData?.data ?? [];
  const agentSkillUuids = new Set((agentSkillsData?.data ?? []).map((s: Skill) => s.uuid));

  function handleSkillToggle(skillUuid: string, checked: boolean) {
    const newUuids = checked
      ? [...agentSkillUuids, skillUuid]
      : [...agentSkillUuids].filter((u) => u !== skillUuid);
    syncAgentSkills.mutate(
      { agentUuid: uuid, skillUuids: newUuids },
      { onError: () => toast.error("Failed to sync skills") },
    );
  }

  // Derived: success rate from heartbeat runs
  const successCount = heartbeatRuns.filter((r) => r.status === "succeeded").length;
  const successRate = heartbeatRuns.length > 0 ? Math.round((successCount / heartbeatRuns.length) * 100) : null;

  // Average duration from heartbeat runs
  const durations = heartbeatRuns
    .filter((r) => r.started_at && r.finished_at)
    .map((r) => new Date(r.finished_at!).getTime() - new Date(r.started_at!).getTime());
  const avgDurationMs = durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : null;

  function formatAvgDuration(ms: number | null): string {
    if (ms === null) return "—";
    if (ms < 1000) return `${Math.round(ms)}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.round(ms / 60000)}m`;
  }

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
      llm_integration_id: a.llm_integration_id ? String(a.llm_integration_id) : "__none__",
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
      body.llm_integration_id = configDraft.llm_integration_id !== "__none__"
        ? Number(configDraft.llm_integration_id)
        : null;
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
  const transcriptRun = transcriptRunUuid ? heartbeatRuns.find((r) => r.uuid === transcriptRunUuid) : null;

  return (
    <AppLayout title="Agent Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/agents"
          titleNode={
            <InlineTitle
              value={agent.name}
              onSave={(name) =>
                patchAgent.mutate(
                  { uuid, body: { name } },
                  { onError: () => toast.error("Failed to update name") },
                )
              }
            />
          }
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
                    <DropdownMenuItem
                      onClick={() => setShowDeleteConfirm(true)}
                      className="text-sm text-red-threat cursor-pointer focus:text-red-threat focus:bg-red-threat/10"
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-2" />
                      Delete Agent
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
            <TabsTrigger value="dashboard" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <LayoutDashboard className="h-3.5 w-3.5 mr-1" />
              Dashboard
            </TabsTrigger>
            <TabsTrigger value="configuration" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Settings className="h-3.5 w-3.5 mr-1" />
              Configuration
            </TabsTrigger>
            <TabsTrigger value="instructions" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <BookOpen className="h-3.5 w-3.5 mr-1" />
              Instructions
            </TabsTrigger>
            <TabsTrigger value="skills" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Wrench className="h-3.5 w-3.5 mr-1" />
              Skills
            </TabsTrigger>
            <TabsTrigger value="assignments" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Layers className="h-3.5 w-3.5 mr-1" />
              Assignments
            </TabsTrigger>
            <TabsTrigger value="runs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Activity className="h-3.5 w-3.5 mr-1" />
              Runs
            </TabsTrigger>
            <TabsTrigger value="cost" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <DollarSign className="h-3.5 w-3.5 mr-1" />
              Cost
            </TabsTrigger>
            <TabsTrigger value="documentation" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Documentation
            </TabsTrigger>
          </TabsList>
          <DetailPageLayout
            sidebarClassName="mt-4"
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
                          value={configDraft.llm_integration_id}
                          onValueChange={(v) => setConfigDraft({ ...configDraft, llm_integration_id: v })}
                        >
                          <SelectTrigger className="bg-surface border-border text-sm">
                            <SelectValue placeholder="Select integration..." />
                          </SelectTrigger>
                          <SelectContent className="bg-card border-border">
                            <SelectItem value="__none__">None</SelectItem>
                            {llmIntegrations.map((llm) => (
                              <SelectItem key={llm.id} value={String(llm.id)}>
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

            {/* Runs Tab — split pane + transcript sheet */}
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
                            <div
                              key={run.uuid}
                              className={cn(
                                "w-full text-left px-3 py-2.5 border-b border-border transition-colors",
                                isSelected ? "bg-teal/10" : "hover:bg-surface/50",
                              )}
                            >
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <button
                                  type="button"
                                  onClick={() => setSelectedRunUuid(isSelected ? null : run.uuid)}
                                  className="flex items-center gap-2 min-w-0 flex-1"
                                >
                                  <span className="font-mono text-[11px] text-dim">#{run.uuid.slice(-6)}</span>
                                </button>
                                <div className="flex items-center gap-1">
                                  <Badge
                                    variant="outline"
                                    className={cn("text-[10px] px-1.5 py-0", heartbeatStatusClass(run.status))}
                                  >
                                    {run.status === "running" && (
                                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-teal mr-0.5" />
                                    )}
                                    {run.status}
                                  </Badge>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <button
                                        type="button"
                                        className="p-0.5 rounded hover:bg-surface transition-colors text-dim hover:text-foreground"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <MoreHorizontal className="h-3 w-3" />
                                      </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="bg-card border-border">
                                      <DropdownMenuItem
                                        className="text-xs cursor-pointer"
                                        onClick={() => setTranscriptRunUuid(run.uuid)}
                                      >
                                        <Eye className="h-3 w-3 mr-2" />
                                        View Transcript
                                      </DropdownMenuItem>
                                      {run.status === "running" && (
                                        <>
                                          <DropdownMenuSeparator />
                                          <DropdownMenuItem
                                            className="text-xs cursor-pointer text-red-threat focus:text-red-threat"
                                            onClick={() => setShowCancelRunConfirm(run.uuid)}
                                          >
                                            <XCircle className="h-3 w-3 mr-2" />
                                            Cancel Run
                                          </DropdownMenuItem>
                                        </>
                                      )}
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={() => setTranscriptRunUuid(run.uuid)}
                                className="flex items-center justify-between gap-2 w-full"
                              >
                                <span className="text-[11px] text-muted-foreground">
                                  {run.started_at ? relativeTime(run.started_at) : "—"}
                                </span>
                                <span className="font-mono text-[11px] text-dim">
                                  {formatDuration(run.started_at, run.finished_at)}
                                </span>
                              </button>
                            </div>
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
                              <div className="flex items-center gap-2">
                                <Badge
                                  variant="outline"
                                  className={cn("text-xs", heartbeatStatusClass(selectedRun.status))}
                                >
                                  {selectedRun.status === "running" && (
                                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-teal mr-1" />
                                  )}
                                  {selectedRun.status}
                                </Badge>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setTranscriptRunUuid(selectedRun.uuid)}
                                  className="h-6 text-[10px] text-dim hover:text-teal-light px-2"
                                >
                                  <Eye className="h-3 w-3 mr-1" />
                                  Transcript
                                </Button>
                              </div>
                              <div className="flex items-center gap-2">
                                {selectedRun.status === "running" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setShowCancelRunConfirm(selectedRun.uuid)}
                                    className="h-6 text-[10px] border-red-threat/30 text-red-threat hover:bg-red-threat/10 px-2"
                                  >
                                    <XCircle className="h-3 w-3 mr-1" />
                                    Cancel
                                  </Button>
                                )}
                                <span className="font-mono text-[11px] text-dim">#{selectedRun.uuid.slice(-6)}</span>
                              </div>
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

            {/* Run Transcript Panel */}
            {transcriptRun && (
              <RunTranscriptPanel
                runUuid={transcriptRun.uuid}
                runStatus={transcriptRun.status}
                runStartedAt={transcriptRun.started_at}
                runFinishedAt={transcriptRun.finished_at}
                onClose={() => setTranscriptRunUuid(null)}
                onStatusChange={() => {
                  // Invalidate heartbeat runs to get fresh status
                  void refetch();
                }}
              />
            )}

            {/* Cancel Run Confirm Dialog */}
            <ConfirmDialog
              open={showCancelRunConfirm !== null}
              onOpenChange={(open) => { if (!open) setShowCancelRunConfirm(null); }}
              title="Cancel Run"
              description="Are you sure you want to cancel this run? The agent will stop processing immediately."
              confirmLabel="Cancel Run"
              variant="destructive"
              onConfirm={() => {
                if (!showCancelRunConfirm) return;
                cancelRun.mutate(showCancelRunConfirm, {
                  onSuccess: () => {
                    toast.success("Run cancelled");
                    setShowCancelRunConfirm(null);
                    void refetch();
                  },
                  onError: (err) => {
                    toast.error(err instanceof Error ? err.message : "Failed to cancel run");
                    setShowCancelRunConfirm(null);
                  },
                });
              }}
            />

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

            {/* Instructions Tab */}
            <TabsContent value="instructions" className="mt-4">
              <div className="mb-3 flex items-start gap-2 rounded-md bg-teal/5 border border-teal/20 px-3 py-2.5">
                <Info className="h-3.5 w-3.5 text-teal mt-0.5 shrink-0" />
                <p className="text-xs text-muted-foreground">
                  Global instructions are configured via Context Documents in the Knowledge Base. Files here are agent-specific instruction files.
                </p>
              </div>
              {filesLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-64 w-full" />
                </div>
              ) : (
                <div className="flex gap-3 h-[600px]">
                  {/* Left: file list */}
                  <div className="w-56 shrink-0 flex flex-col gap-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Files</span>
                      <button
                        type="button"
                        onClick={() => setShowNewFileInput((v) => !v)}
                        className="p-0.5 rounded hover:bg-surface text-dim hover:text-foreground transition-colors"
                        title="New file"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {showNewFileInput && (
                      <div className="flex items-center gap-1 mb-1">
                        <Input
                          autoFocus
                          value={newFileName}
                          onChange={(e) => setNewFileName(e.target.value)}
                          placeholder="AGENTS.md"
                          className="h-7 text-xs bg-surface border-border"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") createNewFile(newFileName);
                            if (e.key === "Escape") {
                              setShowNewFileInput(false);
                              setNewFileName("");
                            }
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => createNewFile(newFileName)}
                          className="h-7 w-7 flex items-center justify-center rounded bg-teal text-white hover:bg-teal-dim shrink-0"
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                    <div className="flex-1 overflow-y-auto rounded-md border border-border bg-card">
                      {(() => {
                        // pendingCreates: files created via + not yet returned by the API
                        const pending = pendingCreates
                          .filter((name) => !agentFiles.some((f) => f.name === name))
                          .map((name) => ({ name, content: "" }));
                        const displayFiles = [...pending, ...agentFiles];
                        if (displayFiles.length === 0) {
                          return (
                            <div className="py-8 text-center text-xs text-dim">No instruction files</div>
                          );
                        }
                        return displayFiles.map((file) => (
                          <button
                            key={file.name}
                            type="button"
                            onClick={() => {
                              setSelectedFile(file.name);
                              setFileContentDraft(file.content);
                              setFileEditorMode("write");
                            }}
                            className={cn(
                              "w-full text-left px-3 py-2 border-b border-border text-xs transition-colors truncate",
                              selectedFile === file.name
                                ? "bg-teal/10 text-teal-light"
                                : "text-foreground hover:bg-surface/50",
                            )}
                          >
                            <FileText className="h-3 w-3 inline mr-1.5 opacity-60" />
                            {file.name}
                          </button>
                        ));
                      })()}
                    </div>
                  </div>

                  {/* Right: markdown editor */}
                  <div className="flex-1 flex flex-col min-w-0">
                    {selectedFile ? (
                      <>
                        {/* Header: Write/Preview tabs + filename + save status */}
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1 bg-surface border border-border rounded-md p-0.5">
                            <button
                              type="button"
                              onClick={() => setFileEditorMode("write")}
                              className={cn(
                                "flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors",
                                fileEditorMode === "write"
                                  ? "bg-teal/15 text-teal-light"
                                  : "text-muted-foreground hover:text-foreground",
                              )}
                            >
                              <Pencil className="h-3 w-3" />
                              Write
                            </button>
                            <button
                              type="button"
                              onClick={() => setFileEditorMode("preview")}
                              className={cn(
                                "flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors",
                                fileEditorMode === "preview"
                                  ? "bg-teal/15 text-teal-light"
                                  : "text-muted-foreground hover:text-foreground",
                              )}
                            >
                              <Eye className="h-3 w-3" />
                              Preview
                            </button>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-muted-foreground">{selectedFile}</span>
                            {saveAgentFile.isPending ? (
                              <span className="flex items-center gap-1 text-[11px] text-dim">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Saving…
                              </span>
                            ) : (
                              <Button
                                size="sm"
                                onClick={() => doSaveFile(selectedFile, fileContentDraft)}
                                className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                              >
                                <Save className="h-3 w-3 mr-1" />
                                Save
                              </Button>
                            )}
                          </div>
                        </div>
                        {fileEditorMode === "write" ? (
                          <>
                            {/* Formatting toolbar */}
                            <TooltipProvider>
                              <div className="flex items-center gap-0.5 px-1 py-1 border border-b-0 border-border bg-muted/20 rounded-t-md">
                                {[
                                  { icon: <Bold className="h-3.5 w-3.5" />, label: "Bold", action: () => wrapFileSelection("**", "**") },
                                  { icon: <Italic className="h-3.5 w-3.5" />, label: "Italic", action: () => wrapFileSelection("*", "*") },
                                  { icon: <Heading2 className="h-3.5 w-3.5" />, label: "Heading", action: () => prependFileLines("## ") },
                                  { icon: <List className="h-3.5 w-3.5" />, label: "Bullet list", action: () => prependFileLines("- ") },
                                  { icon: <Code2 className="h-3.5 w-3.5" />, label: "Code block", action: () => wrapFileSelection("```\n", "\n```") },
                                  { icon: <Link2 className="h-3.5 w-3.5" />, label: "Link", action: () => wrapFileSelection("[", "](url)") },
                                ].map(({ icon, label, action }) => (
                                  <Tooltip key={label}>
                                    <TooltipTrigger asChild>
                                      <button
                                        type="button"
                                        onMouseDown={(e) => { e.preventDefault(); action(); }}
                                        className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                      >
                                        {icon}
                                      </button>
                                    </TooltipTrigger>
                                    <TooltipContent side="top" className="text-xs">{label}</TooltipContent>
                                  </Tooltip>
                                ))}
                              </div>
                            </TooltipProvider>
                            <Textarea
                              ref={fileTextareaRef}
                              value={fileContentDraft}
                              onChange={(e) => setFileContentDraft(e.target.value)}
                              className="flex-1 font-mono text-xs bg-surface border-border resize-none rounded-t-none"
                              placeholder="Write your markdown content here..."
                            />
                          </>
                        ) : (
                          <div className="flex-1 overflow-y-auto rounded-md border border-border bg-card px-4 py-3">
                            {fileContentDraft ? (
                              <MarkdownPreview content={fileContentDraft} />
                            ) : (
                              <p className="text-xs text-dim italic">Nothing to preview</p>
                            )}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="flex-1 flex items-center justify-center rounded-md border border-dashed border-border">
                        <p className="text-sm text-dim">Select a file to edit</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Skills Tab */}
            <TabsContent value="skills" className="mt-4 space-y-4">
              <div className="flex items-start gap-2 rounded-md bg-teal/5 border border-teal/20 px-3 py-2.5">
                <Info className="h-3.5 w-3.5 text-teal mt-0.5 shrink-0" />
                <p className="text-xs text-muted-foreground">
                  Check the skills you want to assign to this agent. Changes sync immediately.{" "}
                  <span className="text-teal">
                    <a href="/skills" className="hover:underline">Manage the skills library</a>
                  </span>
                </p>
              </div>

              {allSkills.length === 0 ? (
                <Card className="bg-card border-border">
                  <CardContent className="py-10 text-center">
                    <Wrench className="h-6 w-6 text-dim mx-auto mb-2" />
                    <p className="text-sm text-dim">No skills in the library yet.</p>
                    <p className="text-xs text-dim/70 mt-1">
                      <a href="/skills" className="text-teal hover:underline">Create a skill</a> to get started.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="bg-card border-border">
                  <CardContent className="p-0">
                    {allSkills.map((skill) => {
                      const isAssigned = agentSkillUuids.has(skill.uuid);
                      return (
                        <div
                          key={skill.uuid}
                          className={cn(
                            "flex items-start gap-3 px-4 py-3 border-b border-border last:border-0 transition-colors",
                            isAssigned && "bg-teal/5",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={isAssigned}
                            onChange={(e) => handleSkillToggle(skill.uuid, e.target.checked)}
                            className="mt-0.5 h-3.5 w-3.5 rounded accent-teal cursor-pointer"
                            disabled={syncAgentSkills.isPending}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-xs font-medium text-foreground">{skill.name}</span>
                              <code className="text-[10px] bg-muted px-1 rounded text-dim">{skill.slug}.md</code>
                              {!skill.is_active && (
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-dim border-dim/30">inactive</Badge>
                              )}
                              {isAssigned && (
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-teal border-teal/30 bg-teal/10">
                                  <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                                  assigned
                                </Badge>
                              )}
                            </div>
                            {skill.description && (
                              <p className="text-xs text-muted-foreground truncate">{skill.description}</p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            {/* Dashboard Tab */}
            <TabsContent value="dashboard" className="mt-4 space-y-4">
              {/* Metric cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Card className="bg-card border-border">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center gap-2 mb-1">
                      <Activity className="h-3.5 w-3.5 text-teal" />
                      <span className="text-xs text-muted-foreground">Total Runs</span>
                    </div>
                    <p className="text-2xl font-semibold text-foreground">{heartbeatRuns.length || "—"}</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingUp className="h-3.5 w-3.5 text-teal" />
                      <span className="text-xs text-muted-foreground">Success Rate</span>
                    </div>
                    <p className="text-2xl font-semibold text-foreground">
                      {successRate !== null ? `${successRate}%` : "—"}
                    </p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="h-3.5 w-3.5 text-teal" />
                      <span className="text-xs text-muted-foreground">Avg Duration</span>
                    </div>
                    <p className="text-2xl font-semibold text-foreground">{formatAvgDuration(avgDurationMs)}</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center gap-2 mb-1">
                      <DollarSign className="h-3.5 w-3.5 text-teal" />
                      <span className="text-xs text-muted-foreground">Total Cost</span>
                    </div>
                    <p className="text-2xl font-semibold text-foreground">
                      {costSummary ? formatCents(costSummary.total_cost_cents) : (totalCostCents > 0 ? formatCents(totalCostCents) : "—")}
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Cost summary breakdown */}
              {costSummary && (
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <DollarSign className="h-3.5 w-3.5 text-teal" />
                        Cost Summary
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Input Tokens</p>
                        <p className="text-sm font-mono text-foreground">{costSummary.total_input_tokens.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Output Tokens</p>
                        <p className="text-sm font-mono text-foreground">{costSummary.total_output_tokens.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Total Cost</p>
                        <p className="text-sm font-mono text-foreground">{formatCents(costSummary.total_cost_cents)}</p>
                      </div>
                    </div>
                    {Object.keys(costSummary.by_billing_type).length > 0 && (
                      <div className="mt-4 pt-4 border-t border-border">
                        <p className="text-xs text-muted-foreground mb-2">By Billing Type</p>
                        <div className="flex flex-wrap gap-3">
                          {Object.entries(costSummary.by_billing_type).map(([type, cents]) => (
                            <div key={type} className="flex items-center gap-1.5">
                              <span className="text-xs text-muted-foreground capitalize">{type}:</span>
                              <span className="text-xs font-mono text-foreground">{formatCents(cents)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Recent runs */}
              <Card className="bg-card border-border overflow-hidden">
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
                    <div className="py-10 text-center">
                      <Activity className="h-6 w-6 text-dim mx-auto mb-2" />
                      <p className="text-sm text-dim">No runs yet</p>
                      <p className="text-xs text-dim/70 mt-1">Runs will appear here once the agent starts processing.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-border">
                      {heartbeatRuns.slice(0, 10).map((run) => (
                        <button
                          key={run.uuid}
                          type="button"
                          onClick={() => setTranscriptRunUuid(run.uuid)}
                          className="flex items-center gap-3 px-4 py-2.5 w-full text-left hover:bg-surface/50 transition-colors"
                        >
                          <Badge
                            variant="outline"
                            className={cn("text-[10px] px-1.5 py-0 shrink-0", heartbeatStatusClass(run.status))}
                          >
                            {run.status === "running" && (
                              <span className="inline-block h-1.5 w-1.5 rounded-full bg-teal mr-0.5" />
                            )}
                            {run.status}
                          </Badge>
                          <span className="text-xs text-muted-foreground flex-1">
                            {run.started_at ? relativeTime(run.started_at) : "—"}
                          </span>
                          <span className="font-mono text-xs text-dim shrink-0">
                            {formatDuration(run.started_at, run.finished_at)}
                          </span>
                          <span className="font-mono text-[11px] text-dim shrink-0">
                            #{run.uuid.slice(-6)}
                          </span>
                        </button>
                      ))}
                    </div>
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

      {/* Delete confirm dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Agent"
        description={`Are you sure you want to delete "${agent?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => {
          deleteAgent.mutate(uuid, {
            onSuccess: () => {
              toast.success("Agent deleted");
              navigate({ to: "/agents" });
            },
            onError: () => toast.error("Failed to delete agent"),
          });
        }}
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
