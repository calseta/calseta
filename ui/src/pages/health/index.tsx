import { useMemo, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatPercent } from "@/lib/format";
import {
  Bot,
  Activity,
  DollarSign,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Settings2,
  Plus,
  RefreshCw,
  Server,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  useAgentFleetSummary,
  useControlPlaneDashboard,
  useHealthSources,
  useHealthMetrics,
  useAllHealthMetricConfigs,
  useDeleteHealthMetricConfig,
} from "@/hooks/use-api";
import type { HealthMetricConfig, HealthMetricSeries } from "@/lib/types";
import { MetricCard } from "@/components/health/metric-card";
import { PresetSelector } from "@/components/health/preset-selector";
import { SourceConfigSheet } from "@/components/health/source-config-sheet";
import { CustomMetricForm } from "@/components/health/custom-metric-form";

const tooltipStyle: React.CSSProperties = {
  backgroundColor: "#0d1117",
  border: "1px solid #1e2a25",
  borderRadius: 8,
  color: "#CCD0CF",
  fontSize: 12,
};

const tooltipLabelStyle: React.CSSProperties = { color: "#CCD0CF" };
const tooltipItemStyle: React.CSSProperties = { color: "#7FCAB8" };
const tooltipCursor = { fill: "rgba(77, 125, 113, 0.08)" };

const TIME_WINDOWS = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "24h", value: "24h" },
  { label: "7d", value: "7d" },
] as const;

export function HealthPage() {
  return (
    <AppLayout title="Health">
      <Tabs defaultValue="agents">
        <TabsList variant="line" className="mb-4">
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
          <TabsTrigger value="custom">Custom</TabsTrigger>
        </TabsList>

        <TabsContent value="agents">
          <AgentsTab />
        </TabsContent>
        <TabsContent value="infrastructure">
          <InfrastructureTab />
        </TabsContent>
        <TabsContent value="custom">
          <CustomTab />
        </TabsContent>
      </Tabs>
    </AppLayout>
  );
}

// ---------------------------------------------------------------------------
// Agents Tab
// ---------------------------------------------------------------------------

const runStatusColors: Record<string, string> = {
  Succeeded: "#4D7D71",
  Failed: "#EA591B",
  Running: "#FFBB1A",
  Pending: "#57635F",
};

function AgentsTab() {
  const { data: fleetResp, isLoading: fleetLoading } = useAgentFleetSummary();
  const { data: cpDashResp } = useControlPlaneDashboard();
  const fleet = fleetResp?.data;
  const cpDash = cpDashResp?.data;

  const runStatusData = useMemo(() => {
    if (!fleet) return [];
    return [
      { name: "Succeeded", value: fleet.successful_runs_7d },
      { name: "Failed", value: fleet.failed_runs_7d },
    ].filter((d) => d.value > 0);
  }, [fleet]);

  if (fleetLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="bg-card border-border">
            <CardContent className="p-6">
              <Skeleton className="h-4 w-24 mb-3" />
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const errorRate = fleet && fleet.total_runs_7d > 0
    ? (fleet.failed_runs_7d / fleet.total_runs_7d)
    : 0;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <KpiCard
          icon={Bot}
          label="Fleet Status"
          value={`${fleet?.active_agents ?? 0} / ${fleet?.total_agents ?? 0}`}
          sub="Active / Total agents"
        />
        <KpiCard
          icon={CheckCircle2}
          label="Success Rate (7d)"
          value={fleet ? `${fleet.success_rate_7d.toFixed(1)}%` : "--"}
          sub={`${fleet?.successful_runs_7d ?? 0} of ${fleet?.total_runs_7d ?? 0} runs`}
        />
        <KpiCard
          icon={DollarSign}
          label="Spend MTD"
          value={fleet ? `$${(fleet.total_cost_mtd_cents / 100).toFixed(2)}` : "--"}
          sub="Month to date"
        />
        <KpiCard
          icon={XCircle}
          label="Error Rate (7d)"
          value={formatPercent(errorRate)}
          sub={`${fleet?.failed_runs_7d ?? 0} failed runs`}
          highlight={errorRate > 0.1}
        />
        <KpiCard
          icon={Activity}
          label="Active Investigations"
          value={cpDash?.queue.available ?? 0}
          sub={`${Object.values(cpDash?.queue.active_by_status ?? {}).reduce((a, b) => a + b, 0)} assigned`}
        />
        <KpiCard
          icon={TrendingUp}
          label="Total Runs (7d)"
          value={fleet?.total_runs_7d ?? 0}
          sub="Heartbeat + dispatch runs"
        />
      </div>

      {runStatusData.length > 0 && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Runs by Status (Last 7 Days)
            </CardTitle>
          </CardHeader>
          <CardContent className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={runStatusData} barSize={40}>
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#57635F", fontSize: 11 }} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  cursor={tooltipCursor}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {runStatusData.map((entry) => (
                    <Cell key={entry.name} fill={runStatusColors[entry.name] ?? "#57635F"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Infrastructure Tab
// ---------------------------------------------------------------------------

function InfrastructureTab() {
  const [window, setWindow] = useState<string>("1h");
  const [presetOpen, setPresetOpen] = useState(false);
  const [sourceSheetOpen, setSourceSheetOpen] = useState(false);

  const { data: sourcesResp, refetch: refetchSources } = useHealthSources();
  const sources = sourcesResp?.data ?? [];
  const sourceUuids = sources.map((s) => s.uuid);

  const { data: allConfigs, refetch: refetchConfigs } = useAllHealthMetricConfigs(sourceUuids);
  const infraConfigs = (allConfigs ?? []).filter((c) => c.category !== "custom");

  const metricsSourceUuid = sources[0]?.uuid;
  const deleteConfig = useDeleteHealthMetricConfig();

  const { data: metricsResp, refetch: refetchMetrics } = useHealthMetrics({
    sourceUuid: metricsSourceUuid,
    window,
  });
  const seriesList = metricsResp?.data ?? [];

  const seriesMap = useMemo(() => {
    const map = new Map<number, HealthMetricSeries>();
    for (const s of seriesList) {
      map.set(s.metric_config_id, s);
    }
    return map;
  }, [seriesList]);

  const handleRemove = async (uuid: string) => {
    if (!confirm("Remove this metric?")) return;
    await deleteConfig.mutateAsync(uuid);
  };

  const handleRefresh = () => {
    refetchSources();
    refetchConfigs();
    refetchMetrics();
  };

  if (sources.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setSourceSheetOpen(true)} className="gap-1.5">
            <Settings2 className="h-3.5 w-3.5" />
            Configure Sources
          </Button>
        </div>
        <EmptyState
          title="No infrastructure monitoring configured"
          description="Add a cloud source to get started with infrastructure health monitoring."
          action={
            <Button size="sm" onClick={() => setSourceSheetOpen(true)} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add Source
            </Button>
          }
        />
        <SourceConfigSheet open={sourceSheetOpen} onOpenChange={setSourceSheetOpen} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {TIME_WINDOWS.map((tw) => (
            <Button
              key={tw.value}
              size="sm"
              variant={window === tw.value ? "default" : "ghost"}
              className="h-7 px-2.5 text-xs"
              onClick={() => setWindow(tw.value)}
            >
              {tw.label}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={handleRefresh} className="h-7 w-7 p-0 text-dim hover:text-teal">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setPresetOpen(true)} className="gap-1.5 h-7 text-xs">
            <Plus className="h-3.5 w-3.5" />
            Add Service
          </Button>
          <Button size="sm" variant="outline" onClick={() => setSourceSheetOpen(true)} className="gap-1.5 h-7 text-xs">
            <Settings2 className="h-3.5 w-3.5" />
            Configure Sources
          </Button>
        </div>
      </div>

      {infraConfigs.length === 0 ? (
        <EmptyState
          title="No metrics configured"
          description="Apply a service preset to auto-configure monitoring metrics."
          action={
            <Button size="sm" onClick={() => setPresetOpen(true)} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add Service
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {infraConfigs.map((config) => {
            const matchedSeries = seriesList.find(
              (s) => s.display_name === config.display_name
            ) ?? seriesMap.get(config.health_source_id);
            return (
              <MetricCard
                key={config.uuid}
                config={config}
                datapoints={matchedSeries?.datapoints ?? []}
                latestValue={matchedSeries?.latest_value ?? null}
                onRemove={handleRemove}
              />
            );
          })}
        </div>
      )}

      <PresetSelector
        open={presetOpen}
        onOpenChange={setPresetOpen}
        sources={sources}
        onApplied={handleRefresh}
      />
      <SourceConfigSheet open={sourceSheetOpen} onOpenChange={setSourceSheetOpen} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom Tab
// ---------------------------------------------------------------------------

function CustomTab() {
  const [window, setWindow] = useState<string>("1h");
  const [formOpen, setFormOpen] = useState(false);
  const [sourceSheetOpen, setSourceSheetOpen] = useState(false);

  const { data: sourcesResp, refetch: refetchSources } = useHealthSources();
  const sources = sourcesResp?.data ?? [];
  const sourceUuids = sources.map((s) => s.uuid);

  const { data: allConfigs, refetch: refetchConfigs } = useAllHealthMetricConfigs(sourceUuids);
  const customConfigs = (allConfigs ?? []).filter((c) => c.category === "custom");

  const deleteConfig = useDeleteHealthMetricConfig();

  const metricsSourceUuid = sources[0]?.uuid;
  const { data: metricsResp, refetch: refetchMetrics } = useHealthMetrics({
    sourceUuid: metricsSourceUuid,
    window,
  });
  const seriesList = metricsResp?.data ?? [];

  const handleRemove = async (uuid: string) => {
    if (!confirm("Remove this custom metric?")) return;
    await deleteConfig.mutateAsync(uuid);
  };

  const handleRefresh = () => {
    refetchSources();
    refetchConfigs();
    refetchMetrics();
  };

  if (sources.length === 0) {
    return (
      <div className="space-y-4">
        <EmptyState
          title="No health sources configured"
          description="Add a cloud source first to create custom metrics."
          action={
            <Button size="sm" onClick={() => setSourceSheetOpen(true)} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add Source
            </Button>
          }
        />
        <SourceConfigSheet open={sourceSheetOpen} onOpenChange={setSourceSheetOpen} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {TIME_WINDOWS.map((tw) => (
            <Button
              key={tw.value}
              size="sm"
              variant={window === tw.value ? "default" : "ghost"}
              className="h-7 px-2.5 text-xs"
              onClick={() => setWindow(tw.value)}
            >
              {tw.label}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={handleRefresh} className="h-7 w-7 p-0 text-dim hover:text-teal">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setFormOpen(true)} className="gap-1.5 h-7 text-xs">
            <Plus className="h-3.5 w-3.5" />
            Add Custom Metric
          </Button>
        </div>
      </div>

      {customConfigs.length === 0 ? (
        <EmptyState
          title="No custom metrics configured"
          description="Define custom metrics to monitor specific CloudWatch or Azure Monitor data."
          action={
            <Button size="sm" onClick={() => setFormOpen(true)} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add Custom Metric
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {customConfigs.map((config) => {
            const matchedSeries = seriesList.find(
              (s) => s.display_name === config.display_name
            );
            return (
              <MetricCard
                key={config.uuid}
                config={config}
                datapoints={matchedSeries?.datapoints ?? []}
                latestValue={matchedSeries?.latest_value ?? null}
                onRemove={handleRemove}
              />
            );
          })}
        </div>
      )}

      <CustomMetricForm
        open={formOpen}
        onOpenChange={setFormOpen}
        sources={sources}
        onCreated={handleRefresh}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

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
    <Card className="bg-card border-border hover:border-teal/30 transition-colors">
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal/10">
          <Icon className="h-4.5 w-4.5 text-teal" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{label}</p>
          <p
            className={cn(
              "text-xl font-heading font-extrabold tracking-tight",
              highlight ? "text-amber" : "text-foreground",
            )}
          >
            {value}
          </p>
          <p className="text-[11px] text-dim truncate">{sub}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="bg-card border-border border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <Server className="h-8 w-8 text-dim mb-3" />
        <p className="text-sm font-medium text-foreground mb-1">{title}</p>
        <p className="text-xs text-dim mb-4 max-w-sm">{description}</p>
        {action}
      </CardContent>
    </Card>
  );
}
