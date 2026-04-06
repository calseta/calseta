import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { TablePagination } from "@/components/table-pagination";
import { useAgents, useCreateAgent, useDeleteAgent, useLLMIntegrations } from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { CopyableText } from "@/components/copyable-text";
import { Plus, Trash2, Bot, RefreshCw, X, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const AGENT_COLUMNS: ColumnDef[] = [
  { key: "agent", initialWidth: 180, minWidth: 120 },
  { key: "uuid", initialWidth: 280, minWidth: 200 },
  { key: "endpoint", initialWidth: 220, minWidth: 120 },
  { key: "status", initialWidth: 80, minWidth: 70 },
  { key: "triggers", initialWidth: 150, minWidth: 80 },
  { key: "registered", initialWidth: 120, minWidth: 80 },
  { key: "actions", initialWidth: 44, minWidth: 44, maxWidth: 44 },
];

interface AgentForm {
  name: string;
  description: string;
  agent_type: string;
  role: string;
  execution_mode: string;
  endpoint_url: string;
  adapter_type: string;
  llm_integration_id: string;
  capabilities: string[];
  max_concurrent_alerts: string;
  max_cost_per_alert: string;
  max_investigation_minutes: string;
}

const defaultForm: AgentForm = {
  name: "",
  description: "",
  agent_type: "standalone",
  role: "",
  execution_mode: "external",
  endpoint_url: "",
  adapter_type: "webhook",
  llm_integration_id: "",
  capabilities: [],
  max_concurrent_alerts: "",
  max_cost_per_alert: "",
  max_investigation_minutes: "",
};

export function AgentsPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } = useTableState({});
  const { data, isLoading, refetch, isFetching } = useAgents(params);
  const createAgent = useCreateAgent();
  const deleteAgent = useDeleteAgent();
  const { data: llmData } = useLLMIntegrations();
  const llmIntegrations = llmData?.data ?? [];

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<AgentForm>(defaultForm);
  const [capInput, setCapInput] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);

  const agents = data?.data ?? [];
  const meta = data?.meta;

  function handleOpen() {
    setForm(defaultForm);
    setCapInput("");
    setShowAdvanced(false);
    setErrors({});
    setOpen(true);
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Name is required";
    if (!form.agent_type) errs.agent_type = "Agent type is required";
    if (!form.execution_mode) errs.execution_mode = "Execution mode is required";
    if (form.execution_mode === "external" && !form.endpoint_url.trim()) {
      errs.endpoint_url = "Endpoint URL is required for external agents";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const body: Record<string, unknown> = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      agent_type: form.agent_type,
      role: form.role.trim() || undefined,
      execution_mode: form.execution_mode,
      capabilities: form.capabilities.length > 0 ? form.capabilities : undefined,
      is_active: true,
      trigger_on_sources: [],
      trigger_on_severities: [],
    };

    if (form.execution_mode === "external") {
      body.endpoint_url = form.endpoint_url.trim();
      body.adapter_type = form.adapter_type;
    } else if (form.execution_mode === "managed" && form.llm_integration_id) {
      body.llm_integration_id = parseInt(form.llm_integration_id);
    }

    if (form.max_concurrent_alerts) {
      body.max_concurrent_alerts = parseInt(form.max_concurrent_alerts);
    }
    if (form.max_cost_per_alert) {
      body.max_cost_per_alert_cents = Math.round(parseFloat(form.max_cost_per_alert) * 100);
    }
    if (form.max_investigation_minutes) {
      body.max_investigation_minutes = parseInt(form.max_investigation_minutes);
    }

    createAgent.mutate(body, {
      onSuccess: () => {
        setOpen(false);
        toast.success("Agent registered");
      },
      onError: () => toast.error("Failed to register agent"),
    });
  }

  function addCapability(value: string) {
    const trimmed = value.trim();
    if (trimmed && !form.capabilities.includes(trimmed)) {
      setForm({ ...form, capabilities: [...form.capabilities, trimmed] });
    }
    setCapInput("");
  }

  function removeCapability(cap: string) {
    setForm({ ...form, capabilities: form.capabilities.filter((c) => c !== cap) });
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteAgent.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Agent deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete agent"),
    });
  }

  return (
    <AppLayout title="Agent Registrations">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            <span className="text-xs text-dim">{meta?.total ?? agents.length} agents</span>
          </div>
          <Button size="sm" className="bg-teal text-white hover:bg-teal-dim" onClick={handleOpen}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Register Agent
          </Button>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="agents" columns={AGENT_COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="agent" className="text-dim text-xs">Agent</ResizableTableHead>
                <ResizableTableHead columnKey="uuid" className="text-dim text-xs">UUID</ResizableTableHead>
                <ResizableTableHead columnKey="endpoint" className="text-dim text-xs">Endpoint URL</ResizableTableHead>
                <ResizableTableHead columnKey="status" className="text-dim text-xs">Status</ResizableTableHead>
                <ResizableTableHead columnKey="triggers" className="text-dim text-xs">Triggers</ResizableTableHead>
                <ResizableTableHead columnKey="registered" className="text-dim text-xs">Registered</ResizableTableHead>
                <ResizableTableHead columnKey="actions" className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : agents.map((agent) => (
                    <TableRow key={agent.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          // eslint-disable-next-line @typescript-eslint/no-explicit-any
                          to={`/manage/agents/${agent.uuid}` as any}
                          className="flex items-center gap-2 hover:text-teal transition-colors"
                        >
                          <Bot className="h-3.5 w-3.5 text-teal" />
                          <span className="text-sm text-foreground hover:text-teal">{agent.name}</span>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <CopyableText text={agent.uuid} mono className="text-[11px] text-dim" />
                      </TableCell>
                      <TableCell>
                        {agent.endpoint_url ? <CopyableText text={agent.endpoint_url} mono className="text-[11px] text-dim max-w-48 truncate" /> : <span className="text-[11px] text-dim">—</span>}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={agent.is_active ? "text-teal bg-teal/10 border-teal/30 text-[11px]" : "text-dim bg-dim/10 border-dim/30 text-[11px]"}>
                          {agent.is_active ? "active" : "inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {[
                          ...agent.trigger_on_severities.map((s) => `sev:${s}`),
                          ...agent.trigger_on_sources.map((s) => `src:${s}`),
                        ].join(", ") || "all"}
                      </TableCell>
                      <TableCell className="text-xs text-dim">{formatDate(agent.created_at)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget({ uuid: agent.uuid, name: agent.name })}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && agents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-dim py-12">
                    No agents registered
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </ResizableTable>
        </div>

        {meta && (
          <TablePagination
            page={page}
            pageSize={pageSize}
            totalPages={meta.total_pages}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        )}
      </div>

      {/* Register Agent Modal */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-card border-border max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register Agent</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-5">

            {/* Section 1 — Identity */}
            <div className="space-y-3">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-dim">Identity</p>
              <div>
                <Label className="text-xs text-muted-foreground">
                  Name <span className="text-red-threat">*</span>
                </Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className={cn("mt-1 bg-surface border-border text-sm", errors.name && "border-red-threat")}
                  placeholder="e.g. Triage Specialist"
                />
                {errors.name && <p className="text-[11px] text-red-threat mt-1">{errors.name}</p>}
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Description</Label>
                <Textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={2}
                  className="mt-1 bg-surface border-border text-sm"
                  placeholder="What does this agent do?"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs text-muted-foreground">
                    Agent Type <span className="text-red-threat">*</span>
                  </Label>
                  <Select
                    value={form.agent_type}
                    onValueChange={(v) => setForm({ ...form, agent_type: v })}
                  >
                    <SelectTrigger className={cn("mt-1 bg-surface border-border text-sm", errors.agent_type && "border-red-threat")}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="orchestrator">orchestrator</SelectItem>
                      <SelectItem value="specialist">specialist</SelectItem>
                      <SelectItem value="resolver">resolver</SelectItem>
                      <SelectItem value="standalone">standalone</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Role</Label>
                  <Input
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                    className="mt-1 bg-surface border-border text-sm"
                    placeholder="e.g. Threat Hunter"
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-border" />

            {/* Section 2 — Execution */}
            <div className="space-y-3">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-dim">Execution</p>
              <div>
                <Label className="text-xs text-muted-foreground">
                  Execution Mode <span className="text-red-threat">*</span>
                </Label>
                <Select
                  value={form.execution_mode}
                  onValueChange={(v) => setForm({ ...form, execution_mode: v })}
                >
                  <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="external">external</SelectItem>
                    <SelectItem value="managed">managed</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {form.execution_mode === "external" && (
                <div className="space-y-3">
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Endpoint URL <span className="text-red-threat">*</span>
                    </Label>
                    <Input
                      value={form.endpoint_url}
                      onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                      type="url"
                      className={cn("mt-1 bg-surface border-border text-sm", errors.endpoint_url && "border-red-threat")}
                      placeholder="https://your-agent.example.com/webhook"
                    />
                    {errors.endpoint_url && <p className="text-[11px] text-red-threat mt-1">{errors.endpoint_url}</p>}
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Adapter</Label>
                    <Select
                      value={form.adapter_type}
                      onValueChange={(v) => setForm({ ...form, adapter_type: v })}
                    >
                      <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="http">http</SelectItem>
                        <SelectItem value="webhook">webhook</SelectItem>
                        <SelectItem value="mcp">mcp</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}

              {form.execution_mode === "managed" && (
                <div>
                  <Label className="text-xs text-muted-foreground">LLM Integration</Label>
                  <Select
                    value={form.llm_integration_id}
                    onValueChange={(v) => setForm({ ...form, llm_integration_id: v })}
                  >
                    <SelectTrigger className="mt-1 bg-surface border-border text-sm">
                      <SelectValue placeholder="Select LLM integration..." />
                    </SelectTrigger>
                    <SelectContent>
                      {llmIntegrations.map((llm) => (
                        <SelectItem key={llm.uuid} value={String(llm.uuid)}>
                          {llm.name} — {llm.provider}/{llm.model}
                        </SelectItem>
                      ))}
                      {llmIntegrations.length === 0 && (
                        <SelectItem value="_none" disabled>No integrations configured</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="border-t border-border" />

            {/* Section 3 — Capabilities */}
            <div className="space-y-3">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-dim">Capabilities</p>
              <div>
                <Label className="text-xs text-muted-foreground">Add capabilities (press Enter)</Label>
                <Input
                  value={capInput}
                  onChange={(e) => setCapInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCapability(capInput);
                    }
                  }}
                  className="mt-1 bg-surface border-border text-sm"
                  placeholder="e.g. triage, enrich, escalate"
                />
              </div>
              {form.capabilities.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {form.capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-teal/10 text-teal border border-teal/30"
                    >
                      {cap}
                      <button
                        type="button"
                        onClick={() => removeCapability(cap)}
                        className="hover:text-red-threat transition-colors"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-border" />

            {/* Section 4 — Advanced (collapsible) */}
            <div className="space-y-3">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-dim hover:text-foreground transition-colors"
              >
                {showAdvanced ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                Advanced
              </button>
              {showAdvanced && (
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <Label className="text-xs text-muted-foreground">Max Concurrent Alerts</Label>
                    <Input
                      value={form.max_concurrent_alerts}
                      onChange={(e) => setForm({ ...form, max_concurrent_alerts: e.target.value })}
                      type="number"
                      min={1}
                      className="mt-1 bg-surface border-border text-sm"
                      placeholder="1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Max Cost / Alert ($)</Label>
                    <Input
                      value={form.max_cost_per_alert}
                      onChange={(e) => setForm({ ...form, max_cost_per_alert: e.target.value })}
                      type="number"
                      min={0}
                      step={0.01}
                      className="mt-1 bg-surface border-border text-sm"
                      placeholder="0.00"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Max Investigation (min)</Label>
                    <Input
                      value={form.max_investigation_minutes}
                      onChange={(e) => setForm({ ...form, max_investigation_minutes: e.target.value })}
                      type="number"
                      min={0}
                      className="mt-1 bg-surface border-border text-sm"
                      placeholder="0"
                    />
                  </div>
                </div>
              )}
            </div>

            <Button
              type="submit"
              disabled={createAgent.isPending}
              className="w-full bg-teal text-white hover:bg-teal-dim"
            >
              {createAgent.isPending ? "Registering..." : "Register Agent"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Agent"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
