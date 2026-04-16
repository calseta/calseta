import { type ReactNode, useMemo, useState, useRef, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMetricsSummary, useApprovals, useControlPlaneDashboard, useActions } from "@/hooks/use-api";
import { useDashboardLayout } from "@/hooks/use-dashboard-layout";
import { formatSeconds, formatPercent } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { CardCatalog } from "@/components/dashboard/card-catalog";
import { PRESETS } from "@/components/dashboard/card-registry";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ShieldAlert,
  Clock,
  Clock4,
  Workflow,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  Timer,
  Target,
  RefreshCw,
  FileText,
  Shield,
  Search,
  Bot,
  Link,
  Hourglass,
  Activity,
  Layers,
  Inbox,
  DollarSign,
  ShieldCheck,
  Plus,
  ChevronDown,
  X,
  LayoutDashboard,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Responsive } from "react-grid-layout/legacy";

function useResizeWidth() {
  const [width, setWidth] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((el: HTMLDivElement | null) => {
    // Clean up previous observer
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    if (!el) return;

    // Read initial width synchronously
    const initial = el.getBoundingClientRect().width;
    if (initial > 0) setWidth(initial);

    // Watch for resizes
    observerRef.current = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    observerRef.current.observe(el);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => observerRef.current?.disconnect();
  }, []);

  return { ref, width };
}
import "react-grid-layout/css/styles.css";

const severityColors: Record<string, string> = {
  Critical: "#EA591B",
  High: "#FFBB1A",
  Medium: "#4D7D71",
  Low: "#57635F",
  Informational: "#2a3530",
  Pending: "#1e2a25",
};

const statusColors: Record<string, string> = {
  Open: "#EA591B",
  Triaging: "#FFBB1A",
  Escalated: "#4D7D71",
  Closed: "#57635F",
};

const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Informational", "Pending"];
const STATUS_ORDER = ["Open", "Triaging", "Escalated", "Closed"];

const tooltipStyle: React.CSSProperties = {
  backgroundColor: "#131920",
  border: "1px solid #1e2a25",
  borderRadius: 8,
  color: "#CCD0CF",
  fontSize: 12,
};

const tooltipLabelStyle: React.CSSProperties = {
  color: "#CCD0CF",
};

const tooltipItemStyle: React.CSSProperties = {
  color: "#7FCAB8",
};

const tooltipCursor = {
  fill: "rgba(77, 125, 113, 0.08)",
};

export function DashboardPage() {
  const { data: metricsResp, isLoading: metricsLoading, refetch, isFetching } = useMetricsSummary();
  const { data: approvalsResp } = useApprovals({ status: "pending" });
  const { data: cpDashResp } = useControlPlaneDashboard();
  const { data: pendingActionsResp } = useActions({ status: "pending" });
  const {
    cards: activeCardIds,
    layout,
    activePreset,
    addCard,
    removeCard,
    setPreset,
    resetToDefault,
    handleLayoutChange,
  } = useDashboardLayout();
  const { ref: containerRef, width } = useResizeWidth();

  const [catalogOpen, setCatalogOpen] = useState(false);
  const [presetConfirm, setPresetConfirm] = useState<string | null>(null);

  const metrics = metricsResp?.data;
  const pendingApprovals = approvalsResp?.data?.length ?? 0;
  const cpDash = cpDashResp?.data;
  const pendingActionsCount = pendingActionsResp?.meta?.total ?? 0;

  const severityData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alerts.by_severity)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => SEVERITY_ORDER.indexOf(a.name) - SEVERITY_ORDER.indexOf(b.name))
        : [],
    [metrics],
  );

  const statusData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alerts.by_status ?? {})
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => STATUS_ORDER.indexOf(a.name) - STATUS_ORDER.indexOf(b.name))
        : [],
    [metrics],
  );

  const sourceData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alerts.by_source ?? {})
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
        : [],
    [metrics],
  );

  const providerByTypeData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.platform?.enrichment_providers_by_indicator_type ?? {})
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
        : [],
    [metrics],
  );

  const queueData = useMemo(
    () =>
      metrics?.queue?.queues?.map((q) => ({
        name: q.queue,
        Pending: q.pending,
        "In Progress": q.in_progress,
        "Failed (30d)": q.failed_30d,
      })) ?? [],
    [metrics],
  );

  if (metricsLoading) {
    return (
      <AppLayout title="Dashboard">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="bg-card border-border">
              <CardContent className="p-6">
                <Skeleton className="h-4 w-24 mb-3" />
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      </AppLayout>
    );
  }

  // Build card map: id -> rendered content
  const cardRenderers: Record<string, ReactNode> = {
    // Platform stats
    "ctx-docs": (
      <StatCard icon={FileText} label="Knowledge Base" value={metrics?.platform?.kb_pages ?? 0} />
    ),
    "det-rules": (
      <StatCard icon={Shield} label="Detection Rules" value={metrics?.platform?.detection_rules ?? 0} />
    ),
    "enrich-prov": (
      <StatCard icon={Search} label="Enrichment Providers" value={metrics?.platform?.enrichment_providers ?? 0} />
    ),
    agents: <StatCard icon={Bot} label="Agents" value={metrics?.platform?.agents ?? 0} />,
    "workflows-count": (
      <StatCard icon={Workflow} label="Workflows" value={metrics?.platform?.workflows ?? 0} />
    ),
    "ind-maps": (
      <StatCard icon={Link} label="Indicator Mappings" value={metrics?.platform?.indicator_mappings ?? 0} />
    ),

    // Alert KPIs
    "total-alerts": (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={ShieldAlert}
          label="Total Alerts"
          value={metrics?.alerts.total ?? 0}
          sub={`${metrics?.alerts.active ?? 0} active`}
        />
      </div>
    ),
    mttd: (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Clock}
          label="MTTD"
          value={formatSeconds(metrics?.alerts.mttd_seconds ?? null)}
          sub="Mean Time to Detect"
        />
      </div>
    ),
    mtta: (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Timer}
          label="MTTA"
          value={formatSeconds(metrics?.alerts.mtta_seconds ?? null)}
          sub="Mean Time to Acknowledge"
        />
      </div>
    ),
    mttt: (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Hourglass}
          label="MTTT"
          value={formatSeconds(metrics?.alerts.mttt_seconds ?? null)}
          sub="Mean Time to Triage"
        />
      </div>
    ),
    mttc: (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Target}
          label="MTTC"
          value={formatSeconds(metrics?.alerts.mttc_seconds ?? null)}
          sub="Mean Time to Conclusion"
        />
      </div>
    ),

    // Ops KPIs
    "wf-exec": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Workflow}
          label="Workflow Executions"
          value={metrics?.workflows.executions ?? 0}
          sub={`${formatPercent(metrics?.workflows.success_rate ?? 0)} success`}
        />
      </div>
    ),
    "time-saved": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={TrendingUp}
          label="Time Saved"
          value={`${(metrics?.workflows.estimated_time_saved_hours ?? 0).toFixed(1)}h`}
          sub="Estimated via workflows"
        />
      </div>
    ),
    "fp-rate": (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={AlertTriangle}
          label="False Positive Rate"
          value={formatPercent(metrics?.alerts.false_positive_rate ?? 0)}
          sub="Last 30 days"
        />
      </div>
    ),
    "enrich-cov": (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Activity}
          label="Enrichment Coverage"
          value={formatPercent(metrics?.alerts.enrichment_coverage ?? 0)}
          sub="Alerts enriched"
        />
      </div>
    ),
    "pending-approvals": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={CheckCircle2}
          label="Pending Approvals"
          value={pendingApprovals}
          sub={`${formatPercent(metrics?.approvals.approval_rate ?? 0)} approval rate`}
          highlight={pendingApprovals > 0}
        />
      </div>
    ),

    // Queue KPIs
    "queue-pending": (
      <KpiCard
        icon={Layers}
        label="Queue Pending"
        value={metrics?.queue?.total_pending ?? 0}
        sub={`${metrics?.queue?.total_in_progress ?? 0} in progress`}
        highlight={(metrics?.queue?.total_pending ?? 0) > 10}
      />
    ),
    "queue-oldest": (
      <KpiCard
        icon={Clock4}
        label="Oldest Pending Task"
        value={formatSeconds(metrics?.queue?.oldest_pending_age_seconds ?? null)}
        sub="Task queue age"
        highlight={(metrics?.queue?.oldest_pending_age_seconds ?? 0) > 300}
      />
    ),

    // Charts
    "sev-chart": (
      <ChartCard title="Alerts by Severity" empty={severityData.length === 0} emptyText="No alert data yet">
        <BarChart data={severityData} barSize={32}>
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={tooltipCursor} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {severityData.map((entry) => (
              <Cell key={entry.name} fill={severityColors[entry.name] ?? "#57635F"} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>
    ),
    "status-chart": (
      <ChartCard title="Alerts by Status" empty={statusData.length === 0} emptyText="No alert data yet">
        <BarChart data={statusData} barSize={32}>
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={tooltipCursor} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {statusData.map((entry) => (
              <Cell key={entry.name} fill={statusColors[entry.name] ?? "#57635F"} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>
    ),
    "source-chart": (
      <ChartCard title="Alerts by Source" empty={sourceData.length === 0} emptyText="No source data yet">
        <BarChart data={sourceData} barSize={32}>
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={tooltipCursor} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#4D7D71" />
        </BarChart>
      </ChartCard>
    ),
    "provider-type-chart": (
      <ChartCard
        title="Enrichment Providers by Indicator Type"
        empty={providerByTypeData.length === 0}
        emptyText="No enrichment provider data yet"
      >
        <BarChart data={providerByTypeData} barSize={32}>
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={tooltipCursor} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#4D7D71" />
        </BarChart>
      </ChartCard>
    ),
    "queue-health": (
      <ChartCard title="Queue Health" empty={queueData.length === 0} emptyText="No queue data available">
        <BarChart data={queueData} barSize={20}>
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={tooltipCursor} />
          <Legend wrapperStyle={{ fontSize: 11, color: "#57635F" }} />
          <Bar dataKey="Pending" fill="#FFBB1A" radius={[4, 4, 0, 0]} />
          <Bar dataKey="In Progress" fill="#4D7D71" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Failed (30d)" fill="#EA591B" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartCard>
    ),

    // Workflow performance
    "wf-configured": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Workflow}
          label="Workflows Configured"
          value={metrics?.workflows.total_configured ?? 0}
          sub="Total active workflows"
        />
      </div>
    ),
    "wf-success-rate": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Target}
          label="Workflow Success Rate"
          value={formatPercent(metrics?.workflows.success_rate ?? 0)}
          sub="Last 30 days"
        />
      </div>
    ),
    "approvals-30d": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={CheckCircle2}
          label="Approvals (30d)"
          value={metrics?.approvals.approved_last_30_days ?? 0}
          sub={`${formatPercent(metrics?.approvals.approval_rate ?? 0)} approval rate`}
        />
      </div>
    ),
    "median-approval-time": (
      <div className="h-full" style={{ background: "rgba(255, 187, 26, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Timer}
          label="Median Approval Time"
          value={
            metrics?.approvals.median_response_time_minutes != null
              ? `${metrics.approvals.median_response_time_minutes.toFixed(1)} min`
              : "--"
          }
          sub="Response latency"
        />
      </div>
    ),
    mtte: (
      <div className="h-full" style={{ background: "rgba(234, 89, 27, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Search}
          label="MTTE"
          value={formatSeconds(metrics?.alerts.mean_time_to_enrich_seconds ?? null)}
          sub="Mean Time to Enrich"
        />
      </div>
    ),

    // Control plane widgets
    "cp-queue-depth": (
      <KpiCard
        icon={Inbox}
        label="Alert Queue"
        value={cpDash?.queue.available ?? 0}
        sub={`${Object.values(cpDash?.queue.active_by_status ?? {}).reduce((a, b) => a + b, 0)} assigned`}
        highlight={(cpDash?.queue.available ?? 0) > 10}
      />
    ),
    "cp-agent-fleet": (
      <div className="h-full" style={{ background: "rgba(77, 125, 113, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={Bot}
          label="Agent Fleet"
          value={cpDash?.agents.by_status["active"] ?? 0}
          sub={(() => {
            const paused = cpDash?.agents.by_status["paused"] ?? 0;
            return paused > 0 ? `${paused} paused` : "All agents active";
          })()}
        />
      </div>
    ),
    "cp-costs-mtd": (
      <KpiCard
        icon={DollarSign}
        label="Spend MTD"
        value={cpDash ? `$${cpDash.costs_mtd.total_usd.toFixed(2)}` : "--"}
        sub="Month to date"
      />
    ),
    "cp-pending-actions": (
      <div className="h-full" style={{ background: "rgba(77, 125, 113, 0.04)", borderRadius: "inherit" }}>
        <KpiCard
          icon={ShieldCheck}
          label="Pending Actions"
          value={pendingActionsCount}
          sub={pendingActionsCount > 0 ? "Requires review" : "No pending actions"}
          highlight={pendingActionsCount > 0}
        />
      </div>
    ),

    // Future agent cards (placeholders)
    "agent-avg-cost": (
      <ComingSoonCard title="Avg Cost per Alert" />
    ),
    "agent-resolution-rate": (
      <ComingSoonCard title="Agent Resolution Rate" />
    ),
    "agent-avg-time": (
      <ComingSoonCard title="Avg Investigation Time" />
    ),
    "agent-delegation-chart": (
      <ComingSoonCard title="Agent Delegations" />
    ),
  };

  const currentPresetName = PRESETS.find((p) => p.id === activePreset)?.name ?? "Custom";

  return (
    <AppLayout title="Dashboard">
      <div className="space-y-2">
        <div className="flex justify-end gap-1">
          {/* Preset dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-dim hover:text-teal text-xs gap-1"
              >
                <LayoutDashboard className="h-3 w-3" />
                {currentPresetName}
                <ChevronDown className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 bg-[#0d1117] border-border">
              {PRESETS.map((preset) => (
                <DropdownMenuItem
                  key={preset.id}
                  onClick={() => {
                    if (activePreset === preset.id) return;
                    setPresetConfirm(preset.id);
                  }}
                  className={cn(
                    "text-xs cursor-pointer",
                    activePreset === preset.id && "text-teal",
                  )}
                >
                  <div>
                    <div className="font-medium">{preset.name}</div>
                    <div className="text-dim text-[10px]">{preset.description}</div>
                  </div>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setPresetConfirm("__reset__")}
                className="text-xs cursor-pointer"
              >
                Reset to SOC Overview
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Add card button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCatalogOpen(true)}
            className="h-8 px-2 text-dim hover:text-teal text-xs gap-1"
          >
            <Plus className="h-3 w-3" />
            Add card
          </Button>

          {/* Refresh */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="h-8 w-8 p-0 text-dim hover:text-teal"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          </Button>
        </div>

        <div ref={containerRef} className="w-full">
          {width > 0 && (
            <Responsive
              className="dashboard-grid"
              width={width}
              layouts={{ lg: layout }}
              breakpoints={{ lg: 1024, md: 768, sm: 480 }}
              cols={{ lg: 12, md: 6, sm: 2 }}
              rowHeight={80}
              margin={[12, 12]}
              containerPadding={[0, 0]}
              isDraggable
              isResizable
              draggableHandle=".drag-handle"
              onLayoutChange={(current) => handleLayoutChange(current)}
              useCSSTransforms
            >
              {layout.map((item) => (
                <div key={item.i} className="group/card relative">
                  {/* Drag handle */}
                  <div className="drag-handle absolute top-1 right-7 z-10 flex h-6 w-6 cursor-grab items-center justify-center rounded-md opacity-0 transition-opacity group-hover/card:opacity-100 hover:bg-teal/10 active:cursor-grabbing">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-dim group-hover/card:text-teal"
                    >
                      <circle cx="9" cy="5" r="1" />
                      <circle cx="9" cy="12" r="1" />
                      <circle cx="9" cy="19" r="1" />
                      <circle cx="15" cy="5" r="1" />
                      <circle cx="15" cy="12" r="1" />
                      <circle cx="15" cy="19" r="1" />
                    </svg>
                  </div>
                  {/* Remove button */}
                  <button
                    type="button"
                    onClick={() => removeCard(item.i)}
                    className="absolute top-1 right-1 z-10 flex h-6 w-6 items-center justify-center rounded-md opacity-0 transition-opacity group-hover/card:opacity-100 hover:bg-red-threat/10 text-dim hover:text-red-threat"
                  >
                    <X className="h-3 w-3" />
                  </button>
                  {cardRenderers[item.i] ?? <ComingSoonCard title={item.i} />}
                </div>
              ))}
            </Responsive>
          )}
        </div>
      </div>

      {/* Card catalog sheet */}
      <CardCatalog
        open={catalogOpen}
        onOpenChange={setCatalogOpen}
        activeCardIds={activeCardIds}
        onAddCard={addCard}
      />

      {/* Preset confirmation dialog */}
      <ConfirmDialog
        open={presetConfirm !== null}
        onOpenChange={(open) => { if (!open) setPresetConfirm(null); }}
        title="Switch Dashboard Layout"
        description={
          presetConfirm === "__reset__"
            ? "This will reset your dashboard to the default SOC Overview layout. Any custom card selections and positions will be lost."
            : `This will replace all current cards with the "${PRESETS.find((p) => p.id === presetConfirm)?.name ?? ""}" preset. Any custom card selections and positions will be lost.`
        }
        confirmLabel="Switch Layout"
        variant="default"
        onConfirm={() => {
          if (presetConfirm === "__reset__") {
            resetToDefault();
          } else if (presetConfirm) {
            setPreset(presetConfirm);
          }
          setPresetConfirm(null);
        }}
      />
    </AppLayout>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
}) {
  return (
    <Card className="surface-2 border-border hover:border-teal/20 transition-colors h-full">
      <CardContent className="flex items-center gap-2.5 p-4 h-full">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-teal/10">
          <Icon className="h-3.5 w-3.5 text-teal" />
        </div>
        <div className="min-w-0">
          <p className="micro-label truncate leading-tight">{label}</p>
          <p className="text-base font-heading font-extrabold tracking-tight text-foreground">
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <Card className="surface-2 border-border hover:border-teal/30 transition-colors h-full">
      <CardContent className="flex items-center gap-3 p-4 h-full">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal/10">
          <Icon className="h-4.5 w-4.5 text-teal" />
        </div>
        <div className="min-w-0">
          <p className="micro-label truncate">{label}</p>
          <p
            className={`text-xl font-heading font-extrabold tracking-tight ${
              highlight ? "text-amber" : "text-foreground"
            }`}
          >
            {value}
          </p>
          <p className="text-[11px] text-dim truncate">{sub}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ChartCard({
  title,
  empty,
  emptyText,
  children,
}: {
  title: string;
  empty: boolean;
  emptyText: string;
  children: ReactNode;
}) {
  return (
    <Card className="surface-2 border-border h-full flex flex-col">
      <CardHeader className="pb-2 shrink-0">
        <CardTitle className="micro-label">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0">
        {!empty ? (
          <ResponsiveContainer width="100%" height="100%">
            {children as React.ReactElement}
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-dim">
            {emptyText}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <Card className="bg-card border-border border-dashed h-full flex flex-col">
      <CardContent className="flex-1 flex flex-col items-center justify-center gap-1.5 p-4">
        <Bot className="h-5 w-5 text-dim" />
        <p className="text-xs font-medium text-muted-foreground">{title}</p>
        <p className="text-[10px] text-dim">Coming soon</p>
      </CardContent>
    </Card>
  );
}
