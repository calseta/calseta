import { useState } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
  DocumentationEditor,
} from "@/components/detail-page";
import { WorkflowCodeEditor } from "@/components/workflow-code-editor";
import { CopyableText } from "@/components/copyable-text";
import {
  useWorkflow,
  useWorkflowRuns,
  usePatchWorkflow,
  useTestWorkflow,
  useDeleteWorkflow,
} from "@/hooks/use-api";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { formatDate, riskColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { WORKFLOW_TEMPLATES, type WorkflowTemplate } from "@/lib/workflow-templates";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Play,
  FlaskConical,
  Save,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Settings,
  FileText,
  Shield,
  AlertTriangle,
  GitBranch,
  ShieldCheck,
  FileCode,
  Copy,
  Wifi,
  WifiOff,
  MoreHorizontal,
  Trash2,
  Pencil,
} from "lucide-react";

// Use central INDICATOR_TYPES from types.ts
import { INDICATOR_TYPES as INDICATOR_TYPE_OPTIONS } from "@/lib/types";
const RISK_LEVELS = ["low", "medium", "high", "critical"];
const WORKFLOW_STATES = ["draft", "active", "inactive"];

const WORKFLOW_LLM_INSTRUCTIONS = `You are generating a Calseta workflow — an async Python function that automates a security operation via HTTP calls.

## Interface

\`\`\`python
from app.workflows.context import WorkflowContext, WorkflowResult

async def run(ctx: WorkflowContext) -> WorkflowResult:
    ...
\`\`\`

## Available on \`ctx\`

| Attribute | Type | Description |
|-----------|------|-------------|
| ctx.indicator.type | str | "ip", "domain", "hash_sha256", "url", "email", "account" |
| ctx.indicator.value | str | The IOC value, e.g. "1.2.3.4", "evil.com" |
| ctx.indicator.malice | str | "Pending", "Benign", "Suspicious", "Malicious" |
| ctx.indicator.uuid | str | Unique identifier |
| ctx.indicator.is_enriched | bool | Whether enrichment has run |
| ctx.indicator.enrichment_results | dict or None | Enrichment data by provider |
| ctx.alert | AlertContext or None | None for standalone workflows |
| ctx.alert.title | str | Alert title |
| ctx.alert.severity | str | "Informational", "Low", "Medium", "High", "Critical" |
| ctx.alert.source_name | str | "sentinel", "elastic", "splunk" |
| ctx.alert.status | str | "Open", "Triaging", "Escalated", "Closed" |
| ctx.alert.tags | list[str] | Alert tags |
| ctx.alert.raw_payload | dict | Original source payload |
| ctx.http | httpx.AsyncClient | Async HTTP client for external calls |
| ctx.log | WorkflowLogger | Structured logging: .info(), .warning(), .error(), .debug() |
| ctx.secrets | SecretsAccessor | .get("ENV_VAR_NAME") returns str or None |
| ctx.integrations.okta | OktaClient or None | Pre-authenticated if OKTA_DOMAIN + OKTA_API_TOKEN set |
| ctx.integrations.entra | EntraClient or None | Pre-authenticated if Entra env vars set |

## Return values

\`\`\`python
return WorkflowResult.ok("Success message", data={"key": "value"})
return WorkflowResult.fail("Error message", data={"status_code": 500})
\`\`\`

## HTTP response (httpx.Response)

| Attribute | Description |
|-----------|-------------|
| resp.status_code | int — HTTP status code |
| resp.text | str — response body as string |
| resp.json() | dict — parse response body as JSON |
| resp.headers | dict-like — response headers |
| resp.is_success | bool — True if 2xx |

## Rules

1. The function MUST be \`async def run(ctx)\` — this is the entry point
2. NEVER raise exceptions — always return WorkflowResult.fail()
3. Always \`await\` HTTP calls: \`resp = await ctx.http.get(url)\`
4. Use ctx.secrets.get("KEY") for API keys/tokens, never hardcode
5. Use ctx.log.info("message", key=value) for logging, not print()
6. Wrap HTTP calls in try/except and return WorkflowResult.fail() on error

## Allowed imports

asyncio, base64, collections, copy, datetime, enum, functools, hashlib, hmac, html, http, inspect, io, ipaddress, itertools, json, logging, math, operator, re, statistics, string, textwrap, time, typing, urllib, uuid

## Blocked (will be rejected)

os, subprocess, sys, socket, open(), exec(), eval(), threading, multiprocessing

## Example pattern

\`\`\`python
from app.workflows.context import WorkflowContext, WorkflowResult

async def run(ctx: WorkflowContext) -> WorkflowResult:
    api_url = ctx.secrets.get("API_URL")
    api_token = ctx.secrets.get("API_TOKEN")
    if not api_url or not api_token:
        return WorkflowResult.fail("API_URL and API_TOKEN must be set")

    payload = {
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
    }
    if ctx.alert:
        payload["alert_title"] = ctx.alert.title
        payload["severity"] = ctx.alert.severity

    ctx.log.info("calling_api", url=api_url)
    try:
        resp = await ctx.http.post(
            api_url,
            json=payload,
            headers={"Authorization": f"Bearer {api_token}"},
        )
    except Exception as exc:
        ctx.log.error("request_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    if resp.status_code >= 400:
        return WorkflowResult.fail(
            f"API returned {resp.status_code}",
            data={"status_code": resp.status_code, "response": resp.json()},
        )

    ctx.log.info("success", status=resp.status_code)
    return WorkflowResult.ok(
        f"Completed (HTTP {resp.status_code})",
        data={"response": resp.json()},
    )
\`\`\`
`;

// ---------------------------------------------------------------------------
// Structured test result display
// ---------------------------------------------------------------------------

/** Parse a structured log line (JSON) into a readable row */
function parseLogLine(line: string): { level: string; message: string; ts: string; extra: Record<string, unknown> } | null {
  try {
    const parsed = JSON.parse(line);
    return {
      level: parsed.level ?? "info",
      message: parsed.message ?? "",
      ts: parsed.ts ?? "",
      extra: parsed.extra ?? {},
    };
  } catch {
    return null;
  }
}

/** Extract a human-readable error message + traceback from the raw message string */
function parseErrorMessage(message: string): { summary: string; traceback: string | null } {
  // Pattern: "Workflow run() raised an exception: <error>\nTraceback..."
  const traceIdx = message.indexOf("\nTraceback");
  if (traceIdx === -1) {
    return { summary: message, traceback: null };
  }
  const summary = message.slice(0, traceIdx).trim();
  const traceBlock = message.slice(traceIdx + 1).trim();

  // Extract just the last line (the actual error) and the relevant file line
  const lines = traceBlock.split("\n");
  const errorLine = lines[lines.length - 1] ?? "";
  // Find the workflow file reference (line in "<workflow>")
  const workflowLine = lines.find((l) => l.includes('File "<workflow>"'));
  const codeLine = workflowLine ? lines[lines.indexOf(workflowLine) + 1]?.trim() : null;

  return {
    summary: `${summary}\n${errorLine}`,
    traceback: codeLine
      ? `${workflowLine?.trim()}\n    ${codeLine}\n${errorLine}`
      : traceBlock,
  };
}

const LOG_LEVEL_STYLES: Record<string, string> = {
  info: "text-teal",
  warning: "text-amber",
  error: "text-red-threat",
  debug: "text-dim",
};

function TestResultDisplay({ result }: { result: Record<string, unknown> }) {
  const data = (result as { data?: Record<string, unknown> }).data ?? result;
  const success = data.success as boolean | undefined;
  const message = (data.message as string) ?? "";
  const logOutput = (data.log_output as string) ?? "";
  const durationMs = data.duration_ms as number | undefined;
  const resultData = data.result_data as Record<string, unknown> | undefined;

  // Parse error message
  const isError = success === false;
  const hasException = message.includes("raised an exception");
  const { summary, traceback } = hasException
    ? parseErrorMessage(message)
    : { summary: message, traceback: null };

  // Parse log lines
  const logLines = logOutput
    .split("\n")
    .filter((l) => l.trim())
    .map(parseLogLine)
    .filter(Boolean) as { level: string; message: string; ts: string; extra: Record<string, unknown> }[];

  // Check if result_data has content
  const hasResultData = resultData && Object.keys(resultData).length > 0;

  return (
    <div className="space-y-3">
      {/* Status header */}
      <Card className={cn(
        "border p-3",
        isError
          ? "bg-red-threat/5 border-red-threat/30"
          : "bg-teal/5 border-teal/30",
      )}>
          <div className="flex items-start gap-3">
            {isError ? (
              <XCircle className="h-5 w-5 text-red-threat shrink-0 mt-0.5" />
            ) : (
              <CheckCircle className="h-5 w-5 text-teal shrink-0 mt-0.5" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between">
                <span className={cn(
                  "text-sm font-medium",
                  isError ? "text-red-threat" : "text-teal",
                )}>
                  {isError ? "Test Failed" : "Test Passed"}
                </span>
                {durationMs != null && durationMs > 0 && (
                  <span className="text-[11px] text-dim font-mono">{durationMs}ms</span>
                )}
              </div>
              {hasException ? (
                <div className="mt-2 space-y-2">
                  <p className="text-sm text-foreground">
                    {summary.split("\n").map((line, i) => (
                      <span key={i}>
                        {i > 0 && <br />}
                        {i === summary.split("\n").length - 1 ? (
                          <span className="font-mono text-red-threat">{line}</span>
                        ) : (
                          line
                        )}
                      </span>
                    ))}
                  </p>
                  {traceback && (
                    <details className="group">
                      <summary className="text-[11px] text-dim cursor-pointer hover:text-foreground select-none">
                        Show traceback
                      </summary>
                      <pre className="mt-1.5 text-[11px] font-mono text-dim whitespace-pre-wrap bg-surface rounded p-3 border border-border overflow-x-auto">
                        {traceback}
                      </pre>
                    </details>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground mt-1">{message}</p>
              )}
            </div>
          </div>
      </Card>

      {/* Result data — the data dict from WorkflowResult.ok/fail(data={...}) */}
      {hasResultData && (
        <Card className="bg-card border-border p-4">
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-[11px] text-dim font-medium tracking-wide uppercase">Result Data</p>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(JSON.stringify(resultData, null, 2));
                toast.success("Copied to clipboard");
              }}
              className="text-dim hover:text-foreground transition-colors p-0.5"
              title="Copy result data"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          </div>
          <pre className="text-[12px] font-mono text-foreground whitespace-pre-wrap break-words bg-surface rounded border border-border p-3 max-h-[400px] overflow-auto">
            {JSON.stringify(resultData, null, 2)}
          </pre>
        </Card>
      )}

      {/* Log output */}
      {logLines.length > 0 && (
        <Card className="bg-card border-border p-4">
          <p className="text-[11px] text-dim font-medium tracking-wide uppercase mb-1.5">Log Output</p>
          <div className="rounded bg-surface border border-border divide-y divide-border overflow-hidden">
            {logLines.map((log, i) => {
              const extraEntries = Object.entries(log.extra);
              return (
                <div key={i} className="px-3 py-2 text-[12px] font-mono overflow-hidden">
                  <div className="flex items-start gap-3">
                    <span className={cn("shrink-0 uppercase font-semibold w-12", LOG_LEVEL_STYLES[log.level] ?? "text-dim")}>
                      {log.level}
                    </span>
                    <span className="text-foreground break-all">{log.message}</span>
                  </div>
                  {extraEntries.length > 0 && (
                    <div className="mt-1.5 ml-[60px] rounded border border-border overflow-hidden">
                      <table className="text-[11px] w-full">
                        <tbody className="divide-y divide-border">
                          {extraEntries.map(([k, v]) => {
                            const val = typeof v === "string" ? v : JSON.stringify(v, null, 2);
                            const isLong = val.length > 120;
                            return (
                              <tr key={k} className="align-top">
                                <td className="text-muted-foreground px-2 py-1 whitespace-nowrap bg-card/50 border-r border-border align-top">{k}</td>
                                <td className="text-dim px-2 py-1 max-w-0 w-full group/val">
                                  <div className="flex items-start gap-1">
                                    <div className="min-w-0 flex-1">
                                      {isLong ? (
                                        <details>
                                          <summary className="cursor-pointer hover:text-foreground truncate block">
                                            {val.slice(0, 100)}...
                                          </summary>
                                          <pre className="mt-1 text-[11px] text-dim whitespace-pre-wrap break-all bg-card rounded p-2 border border-border">
                                            {val}
                                          </pre>
                                        </details>
                                      ) : (
                                        <span className="break-all">{val}</span>
                                      )}
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        navigator.clipboard.writeText(val);
                                        toast.success("Copied to clipboard");
                                      }}
                                      className="shrink-0 opacity-0 group-hover/val:opacity-100 transition-opacity text-dim hover:text-foreground p-0.5"
                                      title="Copy value"
                                    >
                                      <Copy className="h-3 w-3" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

export function WorkflowDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { tab: tabParam } = useSearch({ strict: false }) as { tab?: string };
  const initialTab = ["code", "test", "runs", "docs"].includes(tabParam ?? "") ? tabParam! : "code";
  const { data: wfResp, isLoading, refetch, isFetching } = useWorkflow(uuid);
  const { data: runsResp } = useWorkflowRuns(uuid);
  const patchWorkflow = usePatchWorkflow();
  const testWorkflow = useTestWorkflow();
  const deleteWorkflow = useDeleteWorkflow();
  const navigate = useNavigate();

  const [code, setCode] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [testIndicator, setTestIndicator] = useState("1.2.3.4");
  const [testType, setTestType] = useState("ip");
  const [mockResponse, setMockResponse] = useState("{}");
  const [showMock, setShowMock] = useState(false);
  const [liveHttp, setLiveHttp] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editDraft, setEditDraft] = useState<Record<string, unknown>>({});

  const wf = wfResp?.data;
  const runs = runsResp?.data ?? [];

  // Initialize code editor with workflow code
  if (wf && code === null) {
    setCode(wf.code);
  }

  if (isLoading) {
    return (
      <AppLayout title="Workflow">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full mt-4" />
      </AppLayout>
    );
  }

  if (!wf) {
    return (
      <AppLayout title="Workflow">
        <div className="text-center text-dim py-20">Workflow not found</div>
      </AppLayout>
    );
  }

  function openEditDialog() {
    if (!wf) return;
    setEditDraft({
      name: wf.name,
      state: wf.state,
      workflow_type: wf.workflow_type ?? "",
      risk_level: wf.risk_level,
      indicator_types: [...wf.indicator_types],
      timeout_seconds: wf.timeout_seconds,
      retry_count: wf.retry_count,
      approval_mode: wf.approval_mode ?? "always",
      approval_channel: wf.approval_channel ?? "",
      approval_timeout_seconds: wf.approval_timeout_seconds,
      time_saved_minutes: wf.time_saved_minutes ?? 0,
    });
    setEditOpen(true);
  }

  function updateDraft(key: string, value: unknown) {
    setEditDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleSaveEdit() {
    const body: Record<string, unknown> = { ...editDraft };
    delete body.notifier_hint; // UI-only field
    if (body.workflow_type === "") body.workflow_type = null;
    if (body.approval_channel === "") body.approval_channel = null;
    if (body.time_saved_minutes === 0) body.time_saved_minutes = null;

    patchWorkflow.mutate(
      { uuid, body },
      {
        onSuccess: () => {
          toast.success("Workflow updated");
          setEditOpen(false);
        },
        onError: () => toast.error("Failed to update workflow"),
      },
    );
  }

  function handleSave() {
    if (!code) return;
    patchWorkflow.mutate(
      { uuid, body: { code } },
      {
        onSuccess: () => toast.success("Code saved"),
        onError: () => toast.error("Failed to save code"),
      },
    );
  }

  function handleSaveDoc(content: string) {
    patchWorkflow.mutate(
      { uuid, body: { documentation: content } },
      {
        onSuccess: () => toast.success("Documentation saved"),
        onError: () => toast.error("Failed to save documentation"),
      },
    );
  }

  function handleDelete() {
    deleteWorkflow.mutate(uuid, {
      onSuccess: () => {
        toast.success("Workflow deleted");
        navigate({ to: "/workflows" });
      },
      onError: () => toast.error("Failed to delete workflow"),
    });
  }

  async function handleTest() {
    setTestResult(null);

    // Parse mock response JSON (empty = use default)
    let parsedMock: Record<string, unknown> | undefined;
    if (mockResponse.trim() && mockResponse.trim() !== "{}") {
      try {
        parsedMock = JSON.parse(mockResponse);
      } catch {
        toast.error("Mock response is not valid JSON");
        return;
      }
    }

    try {
      const result = await testWorkflow.mutateAsync({
        uuid,
        body: {
          indicator_type: testType,
          indicator_value: testIndicator,
          mock_http_responses: parsedMock || {},
          live_http: liveHttp,
        },
      });
      setTestResult(result);
      // Toast reflects the workflow result, not just the API call
      const data = (result as { data?: Record<string, unknown> }).data;
      if (data?.success === false) {
        toast.error("Test completed — workflow returned failure");
      } else {
        toast.success("Test completed — workflow returned success");
      }
    } catch (err) {
      setTestResult({ error: String(err) });
      toast.error("Test request failed");
    }
  }

  return (
    <AppLayout title="Workflow Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/workflows"
          title={wf.name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  wf.state === "active"
                    ? "text-teal bg-teal/10 border-teal/30"
                    : "text-amber bg-amber/10 border-amber/30",
                )}
              >
                {wf.state}
              </Badge>
              <Badge variant="outline" className={cn("text-xs", riskColor(wf.risk_level))}>
                {wf.risk_level} risk
              </Badge>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  wf.approval_mode === "always"
                    ? "text-amber bg-amber/10 border-amber/30"
                    : wf.approval_mode === "agent_only"
                      ? "text-teal bg-teal/10 border-teal/30"
                      : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {wf.approval_mode === "agent_only" ? "agent only" : wf.approval_mode} approval
              </Badge>
            </>
          }
          actions={
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={openEditDialog}
              >
                <Pencil className="h-3.5 w-3.5 mr-1.5" />
                Edit
              </Button>
              {wf.state !== "active" && !wf.is_system && (
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
              )}
            </div>
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "State",
              icon: Shield,
              value: (
                <Select
                  value={wf.state}
                  onValueChange={(v) => {
                    patchWorkflow.mutate(
                      { uuid, body: { state: v } },
                      {
                        onSuccess: () => {
                          toast.success(`State changed to ${v}`);
                          void refetch();
                        },
                        onError: () => toast.error("Failed to update state"),
                      },
                    );
                  }}
                >
                  <SelectTrigger
                    className={cn(
                      "h-7 w-full text-xs border",
                      wf.state === "active"
                        ? "text-teal bg-teal/10 border-teal/30"
                        : "text-amber bg-amber/10 border-amber/30",
                    )}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {WORKFLOW_STATES.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Risk Level",
              icon: AlertTriangle,
              value: (
                <Select
                  value={wf.risk_level}
                  onValueChange={(v) => {
                    patchWorkflow.mutate(
                      { uuid, body: { risk_level: v } },
                      {
                        onSuccess: () => toast.success(`Risk level changed to ${v}`),
                        onError: () => toast.error("Failed to update risk level"),
                      },
                    );
                  }}
                >
                  <SelectTrigger className={cn("h-7 w-full text-xs border", riskColor(wf.risk_level))}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {RISK_LEVELS.map((r) => (
                      <SelectItem key={r} value={r}>{r}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Version",
              icon: GitBranch,
              value: <span className="font-mono">v{wf.code_version}</span>,
            },
            {
              label: "Approval",
              icon: ShieldCheck,
              value: (
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    wf.approval_mode === "always"
                      ? "text-amber bg-amber/10 border-amber/30"
                      : wf.approval_mode === "agent_only"
                        ? "text-teal bg-teal/10 border-teal/30"
                        : "text-dim bg-dim/10 border-dim/30",
                  )}
                >
                  {wf.approval_mode === "agent_only" ? "agent only" : wf.approval_mode}
                </Badge>
              ),
            },
          ]}
        />

        <Tabs defaultValue={initialTab}>
          <TabsList className="bg-surface border border-border">
            <TabsTrigger value="code" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileCode className="h-3.5 w-3.5 mr-1" />
              Code
            </TabsTrigger>
            <TabsTrigger value="test" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FlaskConical className="h-3.5 w-3.5 mr-1" />
              Test
            </TabsTrigger>
            <TabsTrigger value="runs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Play className="h-3.5 w-3.5 mr-1" />
              Runs ({runs.length})
            </TabsTrigger>
            <TabsTrigger value="docs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Documentation
            </TabsTrigger>
          </TabsList>

          <DetailPageLayout
            sidebar={
              <DetailPageSidebar>
                <SidebarSection title="Identity">
                <div>
                  <span className="text-xs text-muted-foreground">UUID</span>
                  <div className="mt-1">
                    <CopyableText text={wf.uuid} mono className="text-[11px] text-dim" />
                  </div>
                </div>
              </SidebarSection>
              <SidebarSection title="Configuration">
                <DetailPageField label="Type" value={wf.workflow_type ?? "—"} />
                {wf.indicator_types.length > 0 && (
                  <div>
                    <span className="text-xs text-muted-foreground">Indicator types</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {wf.indicator_types.map((t) => (
                        <Badge key={t} variant="outline" className="text-[10px] text-foreground border-border">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                <DetailPageField label="Timeout" value={`${wf.timeout_seconds}s`} />
                <DetailPageField label="Retry Count" value={String(wf.retry_count)} />
                {wf.time_saved_minutes && (
                  <DetailPageField label="Time Saved" value={`${wf.time_saved_minutes} min`} />
                )}
                <DetailPageField label="System" value={wf.is_system ? "Yes" : "No"} />
              </SidebarSection>
              {wf.approval_mode !== "never" && (
                <SidebarSection title="Approval">
                  <DetailPageField label="Mode" value={wf.approval_mode === "agent_only" ? "Agent Only" : "Always"} />
                  <DetailPageField label="Channel" value={wf.approval_channel ?? "—"} />
                  <DetailPageField label="Timeout" value={`${wf.approval_timeout_seconds}s`} />
                </SidebarSection>
              )}
              <SidebarSection title="Timestamps">
                <DetailPageField label="Created" value={formatDate(wf.created_at)} />
                <DetailPageField label="Updated" value={formatDate(wf.updated_at)} />
              </SidebarSection>
            </DetailPageSidebar>
          }
        >

            {/* Code Editor */}
            <TabsContent value="code" className="mt-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-dim font-mono">v{wf.code_version}</span>
                </div>
                {!wf.is_system && (
                  <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-border text-xs text-dim hover:text-foreground"
                    onClick={() => {
                      navigator.clipboard.writeText(WORKFLOW_LLM_INSTRUCTIONS);
                      toast.success("LLM instructions copied to clipboard");
                    }}
                  >
                    <Copy className="h-3.5 w-3.5 mr-1.5" />
                    Copy LLM Instructions
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-border text-xs text-dim hover:text-foreground"
                      >
                        <FileCode className="h-3.5 w-3.5 mr-1.5" />
                        Use Template
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-80 bg-card border-border">
                      {WORKFLOW_TEMPLATES.map((tpl: WorkflowTemplate) => (
                        <DropdownMenuItem
                          key={tpl.id}
                          onClick={() => setCode(tpl.code)}
                          className="flex flex-col items-start gap-0.5 py-2.5 cursor-pointer"
                        >
                          <span className="text-sm text-foreground font-medium">{tpl.name}</span>
                          <span className="text-[11px] text-dim leading-tight">{tpl.description}</span>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                  </div>
                )}
              </div>
              <WorkflowCodeEditor
                value={code ?? ""}
                onChange={(val) => setCode(val)}
                onSave={handleSave}
                height="500px"
              />
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={patchWorkflow.isPending || code === wf.code}
                  className="bg-teal text-white hover:bg-teal-dim"
                >
                  <Save className="h-3.5 w-3.5 mr-1.5" />
                  Save
                </Button>
                {code !== wf.code && (
                  <span className="text-[11px] text-dim">
                    Unsaved changes &middot; {navigator.platform?.includes("Mac") ? "Cmd" : "Ctrl"}+S to save
                  </span>
                )}
              </div>
            </TabsContent>

            {/* Test Sandbox */}
            <TabsContent value="test" className="mt-4 space-y-4">
              <Card className="bg-card border-border p-4 space-y-2">
                  <div className="flex gap-3">
                    <Select value={testType} onValueChange={setTestType}>
                      <SelectTrigger className="w-48 bg-surface border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-card border-border">
                        {["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"].map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      placeholder="Indicator value"
                      value={testIndicator}
                      onChange={(e) => setTestIndicator(e.target.value)}
                      className="flex-1 bg-surface border-border text-sm"
                    />
                    <Button
                      size="sm"
                      onClick={handleTest}
                      disabled={testWorkflow.isPending}
                      className={cn(
                        "border",
                        liveHttp
                          ? "bg-teal text-white hover:bg-teal-dim border-teal/30"
                          : "bg-card border-border text-foreground hover:border-teal/40",
                      )}
                    >
                      {testWorkflow.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      ) : (
                        <FlaskConical className="h-3.5 w-3.5 mr-1.5" />
                      )}
                      Test
                    </Button>
                  </div>

                  {/* Live / Mock toggle */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setLiveHttp(!liveHttp)}
                        className={cn(
                          "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border transition-colors",
                          liveHttp
                            ? "bg-teal/15 border-teal/40 text-teal-light"
                            : "bg-surface border-border text-dim hover:border-teal/30",
                        )}
                      >
                        {liveHttp ? (
                          <Wifi className="h-3 w-3" />
                        ) : (
                          <WifiOff className="h-3 w-3" />
                        )}
                        {liveHttp ? "Live HTTP" : "Mock HTTP"}
                      </button>
                      <span className="text-[10px] text-dim">
                        {liveHttp
                          ? "Real HTTP requests will be made to external endpoints"
                          : "All HTTP calls return mock responses — no real requests"}
                      </span>
                    </div>
                  </div>

                  {/* Mock response editor (only when mock mode) */}
                  {!liveHttp && (
                    <div className="space-y-2">
                      <button
                        type="button"
                        onClick={() => setShowMock(!showMock)}
                        className="text-[11px] text-dim hover:text-foreground transition-colors flex items-center gap-1.5 select-none"
                      >
                        <span className={cn(
                          "inline-block transition-transform text-[9px]",
                          showMock ? "rotate-90" : "",
                        )}>
                          &#9654;
                        </span>
                        Custom Mock Response
                        {mockResponse.trim() && mockResponse.trim() !== "{}" && (
                          <span className="text-teal ml-1">(set)</span>
                        )}
                      </button>
                      {showMock && (
                        <div className="space-y-1.5">
                          <textarea
                            value={mockResponse}
                            onChange={(e) => setMockResponse(e.target.value)}
                            placeholder='{"ip": "8.8.8.8", "org": "Google LLC", "city": "Mountain View"}'
                            rows={5}
                            className="w-full bg-surface border border-border rounded-md p-3 text-xs font-mono text-foreground resize-y focus:outline-none focus:border-teal/50"
                          />
                          <p className="text-[10px] text-dim leading-relaxed">
                            JSON to return for all HTTP calls. Leave empty for default <span className="font-mono">{"{"}&quot;status&quot;: &quot;ok&quot;{"}"}</span>.
                          </p>
                        </div>
                      )}
                    </div>
                  )}
              </Card>
              {testResult && <TestResultDisplay result={testResult} />}
            </TabsContent>

            {/* Run History */}
            <TabsContent value="runs" className="mt-4">
              {runs.length > 0 ? (
                <div className="space-y-2">
                  {runs.map((run) => (
                    <Card key={run.uuid} className="bg-card border-border">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            {run.status === "completed" ? (
                              <CheckCircle className="h-4 w-4 text-teal" />
                            ) : run.status === "failed" ? (
                              <XCircle className="h-4 w-4 text-red-threat" />
                            ) : (
                              <Clock className="h-4 w-4 text-amber" />
                            )}
                            <div>
                              <span className="text-sm text-foreground">
                                {run.trigger_type} trigger
                              </span>
                              <span className="text-xs text-dim ml-2 font-mono">
                                v{run.code_version_executed}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-dim">
                            {run.duration_ms != null && (
                              <span>{run.duration_ms}ms</span>
                            )}
                            <span>{formatDate(run.created_at)}</span>
                          </div>
                        </div>
                        {run.log_output && (
                          <pre className="mt-2 text-[11px] text-muted-foreground font-mono whitespace-pre-wrap max-h-32 overflow-auto bg-surface p-2 rounded">
                            {run.log_output}
                          </pre>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <div className="text-center text-sm text-dim py-12">
                  No runs recorded yet
                </div>
              )}
            </TabsContent>

            {/* Documentation */}
            <TabsContent value="docs" className="mt-4">
              <DocumentationEditor
                content={wf.documentation ?? ""}
                onSave={handleSaveDoc}
                isSaving={patchWorkflow.isPending}
              />
            </TabsContent>
        </DetailPageLayout>
        </Tabs>
      </div>

      {/* Edit Workflow Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">Edit Workflow</DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            {/* Name */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Name</Label>
              <Input
                value={(editDraft.name as string) ?? ""}
                onChange={(e) => updateDraft("name", e.target.value)}
                className="bg-surface border-border text-sm"
              />
            </div>

            {/* State + Risk Level row */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">State</Label>
                <Select
                  value={editDraft.state as string}
                  onValueChange={(v) => updateDraft("state", v)}
                >
                  <SelectTrigger className="bg-surface border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WORKFLOW_STATES.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Risk Level</Label>
                <Select
                  value={editDraft.risk_level as string}
                  onValueChange={(v) => updateDraft("risk_level", v)}
                >
                  <SelectTrigger className="bg-surface border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RISK_LEVELS.map((r) => (
                      <SelectItem key={r} value={r}>{r}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Type */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Type</Label>
              <Input
                value={(editDraft.workflow_type as string) ?? ""}
                onChange={(e) => updateDraft("workflow_type", e.target.value)}
                placeholder="e.g. enrichment, response, notification"
                className="bg-surface border-border text-sm"
              />
            </div>

            {/* Indicator Types */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Indicator Types</Label>
              <div className="flex flex-wrap gap-2">
                {INDICATOR_TYPE_OPTIONS.map((t) => {
                  const types = (editDraft.indicator_types as string[]) ?? [];
                  const selected = types.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => {
                        const next = selected
                          ? types.filter((x) => x !== t)
                          : [...types, t];
                        updateDraft("indicator_types", next);
                      }}
                      className={cn(
                        "px-2.5 py-1 rounded-md text-xs border transition-colors",
                        selected
                          ? "bg-teal/15 border-teal/40 text-teal-light"
                          : "bg-surface border-border text-dim hover:border-teal/30",
                      )}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Timeout + Retry */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Timeout (seconds)</Label>
                <Input
                  type="number"
                  min={1}
                  value={editDraft.timeout_seconds as number}
                  onChange={(e) => updateDraft("timeout_seconds", parseInt(e.target.value) || 1)}
                  className="bg-surface border-border text-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Retry Count</Label>
                <Input
                  type="number"
                  min={0}
                  value={editDraft.retry_count as number}
                  onChange={(e) => updateDraft("retry_count", parseInt(e.target.value) || 0)}
                  className="bg-surface border-border text-sm"
                />
              </div>
            </div>

            {/* Approval Gate */}
            <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Approval Mode</Label>
                <Select
                  value={editDraft.approval_mode as string}
                  onValueChange={(v) => updateDraft("approval_mode", v)}
                >
                  <SelectTrigger className="bg-card border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="always">Always</SelectItem>
                    <SelectItem value="agent_only">Agent Only</SelectItem>
                    <SelectItem value="never">Never</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {(editDraft.approval_mode as string) !== "never" && (
                <>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Notifier</Label>
                    <Select
                      value={(editDraft.notifier_hint as string) ?? "slack"}
                      onValueChange={(v) => updateDraft("notifier_hint", v)}
                    >
                      <SelectTrigger className="bg-card border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="slack">Slack</SelectItem>
                        <SelectItem value="teams">Microsoft Teams</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-[10px] text-dim">
                      Set globally via <span className="font-mono">APPROVAL_NOTIFIER</span> env var
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">
                      {(editDraft.notifier_hint ?? "slack") === "slack"
                        ? "Slack Channel"
                        : "Teams Webhook URL"}
                    </Label>
                    <Input
                      value={(editDraft.approval_channel as string) ?? ""}
                      onChange={(e) => updateDraft("approval_channel", e.target.value)}
                      placeholder={
                        (editDraft.notifier_hint ?? "slack") === "slack"
                          ? "C0123456789"
                          : "https://outlook.office.com/webhook/..."
                      }
                      className="bg-card border-border text-sm font-mono"
                    />
                    <p className="text-[10px] text-dim">
                      {(editDraft.notifier_hint ?? "slack") === "slack"
                        ? "Use the channel ID (right-click channel → View channel details → copy ID at bottom)"
                        : "Paste the incoming webhook URL from your Teams channel connector"}
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Approval Timeout (seconds)</Label>
                    <Input
                      type="number"
                      min={60}
                      value={editDraft.approval_timeout_seconds as number}
                      onChange={(e) => updateDraft("approval_timeout_seconds", parseInt(e.target.value) || 300)}
                      className="bg-card border-border text-sm"
                    />
                  </div>
                </>
              )}
            </div>

            {/* Time Saved */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Est. Time Saved (minutes)</Label>
              <Input
                type="number"
                min={0}
                value={editDraft.time_saved_minutes as number}
                onChange={(e) => updateDraft("time_saved_minutes", parseInt(e.target.value) || 0)}
                className="bg-surface border-border text-sm"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditOpen(false)}
              className="border-border"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveEdit}
              disabled={patchWorkflow.isPending || !(editDraft.name as string)?.trim()}
              className="bg-teal text-white hover:bg-teal-dim"
            >
              {patchWorkflow.isPending ? (
                <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5 mr-1.5" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Workflow"
        description={`Are you sure you want to delete "${wf.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
