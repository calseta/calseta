import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HealthMetricConfig, HealthMetricDatapoint } from "@/lib/types";

interface MetricCardProps {
  config: HealthMetricConfig;
  datapoints: HealthMetricDatapoint[];
  latestValue: number | null;
  onRemove?: (uuid: string) => void;
}

function formatMetricValue(value: number | null, unit: string): string {
  if (value === null || value === undefined) return "--";
  if (unit === "Percent") return `${value.toFixed(1)}%`;
  if (unit === "Bytes") {
    if (value >= 1e12) return `${(value / 1e12).toFixed(1)} TB`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(1)} GB`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MB`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(1)} KB`;
    return `${Math.round(value)} B`;
  }
  if (unit === "Seconds") {
    if (value < 0.001) return `${(value * 1e6).toFixed(0)} us`;
    if (value < 1) return `${(value * 1000).toFixed(1)} ms`;
    if (value < 60) return `${value.toFixed(2)}s`;
    return `${(value / 60).toFixed(1)}m`;
  }
  if (unit === "Milliseconds") {
    if (value < 1) return `${(value * 1000).toFixed(0)} us`;
    if (value < 1000) return `${value.toFixed(0)} ms`;
    return `${(value / 1000).toFixed(2)}s`;
  }
  if (unit === "Count" || unit === "None") {
    if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
    return value % 1 === 0 ? String(Math.round(value)) : value.toFixed(2);
  }
  return value.toFixed(2);
}

function getThresholdStatus(
  value: number | null,
  warning: number | null,
  critical: number | null,
): "ok" | "warning" | "critical" | "unknown" {
  if (value === null) return "unknown";
  if (critical !== null && value >= critical) return "critical";
  if (warning !== null && value >= warning) return "warning";
  return "ok";
}

const statusDotColors: Record<string, string> = {
  ok: "bg-teal",
  warning: "bg-amber",
  critical: "bg-red-threat",
  unknown: "bg-dim",
};

/**
 * Simple SVG sparkline — no external chart library.
 */
function Sparkline({
  datapoints,
  warning,
  critical,
  className,
}: {
  datapoints: HealthMetricDatapoint[];
  warning: number | null;
  critical: number | null;
  className?: string;
}) {
  const { pathD, areaD, color, viewBox } = useMemo(() => {
    if (datapoints.length < 2) {
      return { pathD: "", areaD: "", color: "#4D7D71", viewBox: "0 0 100 30" };
    }

    const values = datapoints.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const w = 100;
    const h = 30;
    const padding = 2;

    const points = values.map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = padding + ((max - v) / range) * (h - 2 * padding);
      return { x, y };
    });

    const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
    const area = d + ` L ${w} ${h} L 0 ${h} Z`;

    // Determine line color from latest value
    const latest = values[values.length - 1];
    let c = "#4D7D71"; // teal
    if (critical !== null && latest >= critical) c = "#EA591B"; // red
    else if (warning !== null && latest >= warning) c = "#FFBB1A"; // amber

    return { pathD: d, areaD: area, color: c, viewBox: `0 0 ${w} ${h}` };
  }, [datapoints, warning, critical]);

  if (datapoints.length < 2) {
    return (
      <div className={cn("flex items-center justify-center text-[10px] text-dim", className)}>
        No data
      </div>
    );
  }

  return (
    <svg viewBox={viewBox} preserveAspectRatio="none" className={cn("w-full h-full", className)}>
      <path d={areaD} fill={color} opacity={0.1} />
      <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MetricCard({ config, datapoints, latestValue, onRemove }: MetricCardProps) {
  const status = getThresholdStatus(latestValue, config.warning_threshold, config.critical_threshold);

  return (
    <Card className="group bg-card border-border hover:border-teal/20 transition-colors relative">
      {onRemove && (
        <button
          onClick={() => onRemove(config.uuid)}
          className="absolute top-2 right-2 z-10 flex h-5 w-5 items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-threat/10"
          title="Remove metric"
        >
          <X className="h-3 w-3 text-dim hover:text-red-threat" />
        </button>
      )}
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <div className={cn("h-2 w-2 rounded-full shrink-0", statusDotColors[status])} />
          <p className="text-xs text-muted-foreground truncate">{config.display_name}</p>
        </div>
        <div className="flex items-end gap-3">
          <p className="text-2xl font-heading font-extrabold tracking-tight text-foreground leading-none">
            {formatMetricValue(latestValue, config.unit)}
          </p>
          <div className="flex-1 h-8 min-w-0">
            <Sparkline
              datapoints={datapoints}
              warning={config.warning_threshold}
              critical={config.critical_threshold}
              className="h-full"
            />
          </div>
        </div>
        <p className="text-[10px] text-dim truncate">
          {config.namespace} / {config.metric_name} ({config.statistic})
        </p>
      </CardContent>
    </Card>
  );
}
