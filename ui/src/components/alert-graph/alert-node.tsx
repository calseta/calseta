import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useNavigate } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { severityColor, statusColor, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GraphAlertNode } from "@/lib/types";

export const AlertCurrentNode = memo(function AlertCurrentNode({
  data,
}: NodeProps) {
  const alert = data as unknown as GraphAlertNode;

  return (
    <div className="rounded-lg border-2 border-teal bg-card px-4 py-3 shadow-lg shadow-teal/10 min-w-[240px]">
      <Handle type="source" position={Position.Bottom} className="!bg-teal !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-1.5">
        <Badge variant="outline" className={cn("text-[10px]", severityColor(alert.severity))}>
          {alert.severity}
        </Badge>
        <Badge variant="outline" className={cn("text-[10px]", statusColor(alert.status))}>
          {alert.status}
        </Badge>
      </div>
      <p className="text-xs font-medium text-foreground leading-snug truncate max-w-[220px]">
        {alert.title}
      </p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[10px] text-dim">{alert.source_name}</span>
        <span className="text-[10px] text-dim">{relativeTime(alert.occurred_at)}</span>
      </div>
    </div>
  );
});

export const AlertSiblingNode = memo(function AlertSiblingNode({
  data,
}: NodeProps) {
  const alert = data as unknown as GraphAlertNode;
  const navigate = useNavigate();

  return (
    <div
      className="rounded-md border border-border bg-card px-3 py-2 hover:border-teal/40 transition-colors cursor-pointer min-w-[200px]"
      onClick={() => navigate({ to: "/alerts/$uuid", params: { uuid: alert.uuid } })}
    >
      <Handle type="target" position={Position.Top} className="!bg-border !w-1.5 !h-1.5" />
      <div className="flex items-center gap-1.5 mb-1">
        <Badge variant="outline" className={cn("text-[9px]", severityColor(alert.severity))}>
          {alert.severity}
        </Badge>
        <Badge variant="outline" className={cn("text-[9px]", statusColor(alert.status))}>
          {alert.status}
        </Badge>
      </div>
      <p className="text-[11px] text-foreground truncate max-w-[180px]">
        {alert.title}
      </p>
      <span className="text-[9px] text-dim">{relativeTime(alert.occurred_at)}</span>
    </div>
  );
});
