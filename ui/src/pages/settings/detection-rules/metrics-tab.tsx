import { type ReactNode, useMemo, useState, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useDetectionRuleMetrics } from "@/hooks/use-api";
import { formatSeconds, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  ShieldAlert,
  Clock,
  Target,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  Activity,
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
import { Responsive } from "react-grid-layout/legacy";
import type { Layout, LayoutItem } from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";

// ---------------------------------------------------------------------------
// Resize hook (same as dashboard)
// ---------------------------------------------------------------------------

function useResizeWidth() {
  const [width, setWidth] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((el: HTMLDivElement | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    if (!el) return;

    const initial = el.getBoundingClientRect().width;
    if (initial > 0) setWidth(initial);

    observerRef.current = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    observerRef.current.observe(el);
  }, []);

  useEffect(() => {
    return () => observerRef.current?.disconnect();
  }, []);

  return { ref, width };
}

// ---------------------------------------------------------------------------
// Layout hook (localStorage persistence, same pattern as dashboard)
// ---------------------------------------------------------------------------

const STORAGE_KEY = "calseta:rule-metrics-grid:v1";

const DEFAULT_LAYOUT: LayoutItem[] = [
  // Row 0: KPI cards — 4 × 3 cols = 12
  { i: "total-alerts",  x: 0, y: 0, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "active-alerts", x: 3, y: 0, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "fp-rate",       x: 6, y: 0, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "tp-rate",       x: 9, y: 0, w: 3, h: 1, minW: 2, maxW: 6 },

  // Row 1: KPI cards — 2 × 3 cols
  { i: "mtta", x: 0, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "mttc", x: 3, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },

  // Row 2–4: Charts — 2 × 6 cols, 3h each
  { i: "alerts-over-time", x: 0, y: 2, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
  { i: "fp-over-time",     x: 6, y: 2, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 5–7: Charts — 2 × 6 cols, 3h each
  { i: "severity-chart", x: 0, y: 5, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
  { i: "status-chart",   x: 6, y: 5, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 8–10: Charts/Tables — 2 × 6 cols, 3h each
  { i: "close-classifications", x: 0, y: 8,  w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
  { i: "top-indicators",        x: 6, y: 8,  w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 11–13: Charts — 1 × 6 cols, 3h
  { i: "alert-sources", x: 0, y: 11, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
];

function loadLayout(): LayoutItem[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved: LayoutItem[] = JSON.parse(raw);
    const defaultMap = new Map(DEFAULT_LAYOUT.map((l) => [l.i, l]));
    const savedIds = new Set(saved.map((l) => l.i));
    const reconciled = saved.filter((l) => defaultMap.has(l.i));
    for (const dl of DEFAULT_LAYOUT) {
      if (!savedIds.has(dl.i)) reconciled.push(dl);
    }
    return reconciled;
  } catch {
    return null;
  }
}

function saveLayout(layout: readonly LayoutItem[]) {
  try {
    const minimal = layout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(minimal));
  } catch {
    // silently ignore
  }
}

function useRuleMetricsLayout() {
  const [layout, setLayout] = useState<LayoutItem[]>(() => {
    const saved = loadLayout();
    return saved ?? [...DEFAULT_LAYOUT];
  });

  const handleLayoutChange = useCallback((newLayout: Layout) => {
    const defaultMap = new Map(DEFAULT_LAYOUT.map((l) => [l.i, l]));
    const merged = newLayout.map((item) => {
      const defaults = defaultMap.get(item.i);
      return defaults
        ? { ...item, minW: defaults.minW, maxW: defaults.maxW, minH: defaults.minH }
        : { ...item };
    });
    setLayout(merged);
    saveLayout(merged);
  }, []);

  const resetLayout = useCallback(() => {
    setLayout([...DEFAULT_LAYOUT]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // silently ignore
    }
  }, []);

  return { layout, handleLayoutChange, resetLayout };
}

// ---------------------------------------------------------------------------
// Color palettes & tooltip styles (same as dashboard)
// ---------------------------------------------------------------------------

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
  backgroundColor: "#0d1117",
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

const maliceBadgeClass: Record<string, string> = {
  Malicious: "bg-red-500/15 text-red-400 border-red-500/30",
  Suspicious: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  Benign: "bg-green-500/15 text-green-400 border-green-500/30",
  Pending: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

// ---------------------------------------------------------------------------
// Sub-components (same as dashboard)
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
    <Card className="bg-card border-border hover:border-teal/30 transition-colors h-full">
      <CardContent className="flex items-center gap-3 p-4 h-full">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal/10">
          <Icon className="h-4.5 w-4.5 text-teal" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{label}</p>
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
    <Card className="bg-card border-border h-full flex flex-col">
      <CardHeader className="pb-2 shrink-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function DetectionRuleMetricsTab({ uuid }: { uuid: string }) {
  const { data: metricsResp, isLoading, refetch, isFetching } = useDetectionRuleMetrics(uuid);
  const { layout, handleLayoutChange, resetLayout } = useRuleMetricsLayout();
  const { ref: containerRef, width } = useResizeWidth();

  const metrics = metricsResp?.data;

  const severityData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alerts_by_severity)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => SEVERITY_ORDER.indexOf(a.name) - SEVERITY_ORDER.indexOf(b.name))
        : [],
    [metrics],
  );

  const statusData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alerts_by_status)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => STATUS_ORDER.indexOf(a.name) - STATUS_ORDER.indexOf(b.name))
        : [],
    [metrics],
  );

  const classificationData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.close_classifications)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
        : [],
    [metrics],
  );

  const sourceData = useMemo(
    () =>
      metrics
        ? Object.entries(metrics.alert_sources)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
        : [],
    [metrics],
  );

  const alertsOverTimeData = useMemo(
    () => metrics?.alerts_over_time ?? [],
    [metrics],
  );

  const fpOverTimeData = useMemo(
    () => metrics?.fp_over_time ?? [],
    [metrics],
  );

  const topIndicators = useMemo(
    () => metrics?.top_indicators ?? [],
    [metrics],
  );

  // Loading state
  if (isLoading) {
    return (
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
    );
  }

  // Empty state
  if (metrics && metrics.total_alerts === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <ShieldAlert className="h-10 w-10 text-dim mb-3" />
        <p className="text-sm text-muted-foreground">No alerts for this detection rule</p>
        <p className="text-xs text-dim mt-1">
          Metrics will appear once alerts are ingested matching this rule.
        </p>
      </div>
    );
  }

  // Build card map
  const cards: Record<string, ReactNode> = {
    "total-alerts": (
      <KpiCard
        icon={ShieldAlert}
        label="Total Alerts"
        value={metrics?.total_alerts ?? 0}
        sub="All time"
      />
    ),
    "active-alerts": (
      <KpiCard
        icon={Activity}
        label="Active Alerts"
        value={metrics?.active_alerts ?? 0}
        sub="Open + Triaging + Escalated"
      />
    ),
    "fp-rate": (
      <KpiCard
        icon={AlertTriangle}
        label="False Positive Rate"
        value={formatPercent(metrics?.false_positive_rate ?? 0)}
        sub="Closed as false positive"
      />
    ),
    "tp-rate": (
      <KpiCard
        icon={Target}
        label="True Positive Rate"
        value={formatPercent(metrics?.true_positive_rate ?? 0)}
        sub="Closed as true positive"
      />
    ),
    mtta: (
      <KpiCard
        icon={Clock}
        label="MTTA"
        value={formatSeconds(metrics?.mtta_seconds ?? null)}
        sub="Mean Time to Acknowledge"
      />
    ),
    mttc: (
      <KpiCard
        icon={Target}
        label="MTTC"
        value={formatSeconds(metrics?.mttc_seconds ?? null)}
        sub="Mean Time to Conclusion"
      />
    ),

    "alerts-over-time": (
      <ChartCard
        title="Alerts Over Time"
        empty={alertsOverTimeData.length === 0}
        emptyText="No timeline data"
      >
        <BarChart data={alertsOverTimeData} barSize={32}>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} fill="#4D7D71" />
        </BarChart>
      </ChartCard>
    ),

    "fp-over-time": (
      <ChartCard
        title="False Positives Over Time"
        empty={fpOverTimeData.length === 0}
        emptyText="No false positive data"
      >
        <BarChart data={fpOverTimeData} barSize={32}>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} fill="#EA591B" />
        </BarChart>
      </ChartCard>
    ),

    "severity-chart": (
      <ChartCard
        title="Alerts by Severity"
        empty={severityData.length === 0}
        emptyText="No severity data"
      >
        <BarChart data={severityData} barSize={32}>
          <XAxis
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {severityData.map((entry) => (
              <Cell key={entry.name} fill={severityColors[entry.name] ?? "#57635F"} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>
    ),

    "status-chart": (
      <ChartCard
        title="Alerts by Status"
        empty={statusData.length === 0}
        emptyText="No status data"
      >
        <BarChart data={statusData} barSize={32}>
          <XAxis
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {statusData.map((entry) => (
              <Cell key={entry.name} fill={statusColors[entry.name] ?? "#57635F"} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>
    ),

    "close-classifications": (
      <ChartCard
        title="Close Classifications"
        empty={classificationData.length === 0}
        emptyText="No closed alerts yet"
      >
        <BarChart data={classificationData} barSize={32}>
          <XAxis
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#4D7D71" />
        </BarChart>
      </ChartCard>
    ),

    "top-indicators": (
      <Card className="bg-card border-border h-full flex flex-col">
        <CardHeader className="pb-2 shrink-0">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Top Indicators
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-auto">
          {topIndicators.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-dim">
              No indicators extracted
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-left py-1.5 px-1 font-medium">Type</th>
                  <th className="text-left py-1.5 px-1 font-medium">Value</th>
                  <th className="text-right py-1.5 px-1 font-medium">Count</th>
                  <th className="text-right py-1.5 px-1 font-medium">Malice</th>
                </tr>
              </thead>
              <tbody>
                {topIndicators.map((ind, idx) => (
                  <tr key={idx} className="border-b border-border/50 last:border-0">
                    <td className="py-1.5 px-1 text-dim">{ind.type}</td>
                    <td className="py-1.5 px-1 text-foreground font-mono truncate max-w-[140px]">
                      {ind.value}
                    </td>
                    <td className="py-1.5 px-1 text-right text-foreground">{ind.count}</td>
                    <td className="py-1.5 px-1 text-right">
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] px-1.5 py-0",
                          maliceBadgeClass[ind.malice] ?? maliceBadgeClass.Pending,
                        )}
                      >
                        {ind.malice}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    ),

    "alert-sources": (
      <ChartCard
        title="Alert Sources"
        empty={sourceData.length === 0}
        emptyText="No source data"
      >
        <BarChart data={sourceData} barSize={32}>
          <XAxis
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#57635F", fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={tooltipItemStyle}
            cursor={tooltipCursor}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#4D7D71" />
        </BarChart>
      </ChartCard>
    ),
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-end gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={resetLayout}
          className="h-8 px-2 text-dim hover:text-teal text-xs gap-1"
        >
          <RotateCcw className="h-3 w-3" />
          Reset layout
        </Button>
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
            className="rule-metrics-grid"
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
              <div key={item.i} className="group relative">
                <div className="drag-handle absolute top-1 right-1 z-10 flex h-6 w-6 cursor-grab items-center justify-center rounded-md opacity-0 transition-opacity group-hover:opacity-100 hover:bg-teal/10 active:cursor-grabbing">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-dim group-hover:text-teal"
                  >
                    <circle cx="9" cy="5" r="1" />
                    <circle cx="9" cy="12" r="1" />
                    <circle cx="9" cy="19" r="1" />
                    <circle cx="15" cy="5" r="1" />
                    <circle cx="15" cy="12" r="1" />
                    <circle cx="15" cy="19" r="1" />
                  </svg>
                </div>
                {cards[item.i]}
              </div>
            ))}
          </Responsive>
        )}
      </div>
    </div>
  );
}
