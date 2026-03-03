import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
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
import {
  useWorkflow,
  useWorkflowRuns,
  usePatchWorkflow,
  useTestWorkflow,
  useExecuteWorkflow,
} from "@/hooks/use-api";
import { formatDate, relativeTime, riskColor } from "@/lib/format";
import { cn } from "@/lib/utils";
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
} from "lucide-react";

const INDICATOR_TYPE_OPTIONS = ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"];
const RISK_LEVELS = ["low", "medium", "high", "critical"];
const WORKFLOW_STATES = ["draft", "active", "inactive"];

export function WorkflowDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data: wfResp, isLoading, refetch, isFetching } = useWorkflow(uuid);
  const { data: runsResp } = useWorkflowRuns(uuid);
  const patchWorkflow = usePatchWorkflow();
  const testWorkflow = useTestWorkflow();
  const executeWorkflow = useExecuteWorkflow();

  const [code, setCode] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [testIndicator, setTestIndicator] = useState("1.2.3.4");
  const [testType, setTestType] = useState("ip");
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
      requires_approval: wf.requires_approval,
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

  async function handleTest() {
    setTestResult(null);
    try {
      const result = await testWorkflow.mutateAsync({
        uuid,
        body: {
          indicator_type: testType,
          indicator_value: testIndicator,
          mock_http_responses: {},
        },
      });
      setTestResult(result);
      toast.success("Test completed");
    } catch (err) {
      setTestResult({ error: String(err) });
      toast.error("Test failed");
    }
  }

  function handleExecute() {
    executeWorkflow.mutate(
      {
        uuid,
        body: {
          indicator_type: testType,
          indicator_value: testIndicator,
          trigger_source: "human",
        },
      },
      {
        onSuccess: () => toast.success("Workflow execution started"),
        onError: () => toast.error("Failed to execute workflow"),
      },
    );
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
              {wf.requires_approval && (
                <Badge variant="outline" className="text-xs text-amber bg-amber/10 border-amber/30">
                  Approval required
                </Badge>
              )}
            </>
          }
          actions={
            <Button
              size="sm"
              variant="outline"
              onClick={openEditDialog}
              className="border-border text-xs"
            >
              <Settings className="h-3 w-3 mr-1" />
              Edit Workflow
            </Button>
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
                        onSuccess: () => toast.success(`State changed to ${v}`),
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
              value: wf.requires_approval ? "Required" : "Not required",
            },
          ]}
        />

        <DetailPageLayout
          sidebar={
            <DetailPageSidebar>
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
              {wf.requires_approval && (
                <SidebarSection title="Approval">
                  <DetailPageField label="Required" value="Yes" />
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
          <Tabs defaultValue="code">
            <TabsList className="bg-surface border border-border">
              <TabsTrigger value="code" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Code
              </TabsTrigger>
              <TabsTrigger value="test" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Test
              </TabsTrigger>
              <TabsTrigger value="runs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Runs ({runs.length})
              </TabsTrigger>
              <TabsTrigger value="docs" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <FileText className="h-3.5 w-3.5 mr-1" />
                Documentation
              </TabsTrigger>
            </TabsList>

            {/* Code Editor */}
            <TabsContent value="code" className="mt-4 space-y-3">
              <div className="rounded-lg border border-border bg-surface overflow-hidden">
                <textarea
                  value={code ?? ""}
                  onChange={(e) => setCode(e.target.value)}
                  className="w-full h-[500px] p-4 bg-transparent text-sm font-mono text-foreground resize-none outline-none"
                  spellCheck={false}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={patchWorkflow.isPending || code === wf.code}
                  className="bg-teal text-white hover:bg-teal-dim"
                >
                  <Save className="h-3.5 w-3.5 mr-1.5" />
                  Save
                </Button>
              </div>
            </TabsContent>

            {/* Test Sandbox */}
            <TabsContent value="test" className="mt-4 space-y-4">
              <Card className="bg-card border-border">
                <CardContent className="p-4 space-y-3">
                  <div className="flex gap-3">
                    <Input
                      placeholder="Indicator type (ip, domain, hash_sha256...)"
                      value={testType}
                      onChange={(e) => setTestType(e.target.value)}
                      className="w-48 bg-surface border-border text-sm"
                    />
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
                      className="bg-card border border-border text-foreground hover:border-teal/40"
                    >
                      {testWorkflow.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      ) : (
                        <FlaskConical className="h-3.5 w-3.5 mr-1.5" />
                      )}
                      Test
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleExecute}
                      disabled={executeWorkflow.isPending}
                      className="bg-teal text-white hover:bg-teal-dim"
                    >
                      <Play className="h-3.5 w-3.5 mr-1.5" />
                      Execute
                    </Button>
                  </div>
                </CardContent>
              </Card>
              {testResult && (
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm text-muted-foreground">
                      Test Result
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="text-xs font-mono text-foreground whitespace-pre-wrap">
                      {JSON.stringify(testResult, null, 2)}
                    </pre>
                  </CardContent>
                </Card>
              )}
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
                            <span>{relativeTime(run.created_at)}</span>
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
          </Tabs>
        </DetailPageLayout>
      </div>

      {/* Edit Workflow Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">Edit Workflow</DialogTitle>
          </DialogHeader>

          <div className="space-y-5 py-2">
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
              <div className="flex items-center justify-between">
                <Label className="text-sm text-muted-foreground">Requires Approval</Label>
                <Switch
                  checked={editDraft.requires_approval as boolean}
                  onCheckedChange={(v) => updateDraft("requires_approval", v)}
                />
              </div>
              {(editDraft.requires_approval as boolean) && (
                <>
                  <div className="space-y-1.5">
                    <Label className="text-sm text-muted-foreground">Approval Channel</Label>
                    <Input
                      value={(editDraft.approval_channel as string) ?? ""}
                      onChange={(e) => updateDraft("approval_channel", e.target.value)}
                      placeholder="#soc-approvals"
                      className="bg-card border-border text-sm"
                    />
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
    </AppLayout>
  );
}
