import { Badge } from "@/components/ui/badge";
import {
  severityColor,
  statusColor,
  maliceColor,
  formatDate,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GraphAlertNode, GraphIndicatorNode } from "@/lib/types";

interface GraphTooltipProps {
  type: "alert" | "indicator";
  data: GraphAlertNode | GraphIndicatorNode;
  position: { x: number; y: number };
}

export function GraphTooltip({ type, data, position }: GraphTooltipProps) {
  return (
    <div
      className="absolute z-50 rounded-lg border border-border bg-card shadow-lg p-3 min-w-[240px] max-w-[320px] pointer-events-none"
      style={{ left: position.x + 16, top: position.y + 16 }}
    >
      {type === "alert" ? (
        <AlertTooltipContent data={data as GraphAlertNode} />
      ) : (
        <IndicatorTooltipContent data={data as GraphIndicatorNode} />
      )}
    </div>
  );
}

function AlertTooltipContent({ data }: { data: GraphAlertNode }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-foreground">{data.title}</p>
      <div className="flex items-center gap-1.5">
        <Badge variant="outline" className={cn("text-[10px]", severityColor(data.severity))}>
          {data.severity}
        </Badge>
        <Badge variant="outline" className={cn("text-[10px]", statusColor(data.status))}>
          {data.status}
        </Badge>
      </div>
      <div className="text-[11px] text-dim space-y-0.5">
        <div>Source: {data.source_name}</div>
        <div>Occurred: {formatDate(data.occurred_at)}</div>
        <div>{formatDate(data.occurred_at)}</div>
      </div>
      {data.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {data.tags.map((t) => (
            <Badge key={t} variant="outline" className="text-[9px] border-border text-dim">
              {t}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function IndicatorTooltipContent({ data }: { data: GraphIndicatorNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-medium uppercase text-dim">{data.type}</span>
        <Badge variant="outline" className={cn("text-[10px]", maliceColor(data.malice))}>
          {data.malice}
        </Badge>
      </div>
      <p className="text-xs font-mono text-foreground break-all">{data.value}</p>
      <div className="text-[11px] text-dim space-y-0.5">
        <div>First seen: {formatDate(data.first_seen)}</div>
        <div>Last seen: {formatDate(data.last_seen)}</div>
        <div>Total alerts: {data.total_alert_count + 1}</div>
      </div>
      {Object.keys(data.enrichment_summary).length > 0 && (
        <div className="space-y-0.5">
          <span className="text-[10px] text-dim font-medium">Enrichment:</span>
          {Object.entries(data.enrichment_summary).map(([provider, verdict]) => (
            <div key={provider} className="text-[10px] text-dim">
              <span className="text-teal-light">{provider}</span>: {verdict}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
