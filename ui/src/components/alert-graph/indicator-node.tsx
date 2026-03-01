import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";
import { maliceColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Globe, Hash, ExternalLink, Mail, User } from "lucide-react";
import type { GraphIndicatorNode } from "@/lib/types";

const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  ip: Globe,
  domain: Globe,
  url: ExternalLink,
  email: Mail,
  account: User,
  hash_md5: Hash,
  hash_sha1: Hash,
  hash_sha256: Hash,
};

export const IndicatorNode = memo(function IndicatorNode({
  data,
}: NodeProps) {
  const ind = data as unknown as GraphIndicatorNode;
  const Icon = typeIcons[ind.type] ?? Hash;
  const moreCount = ind.total_alert_count - ind.sibling_alerts.length;

  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 min-w-[220px]">
      <Handle type="target" position={Position.Top} className="!bg-teal !w-1.5 !h-1.5" />
      <Handle type="source" position={Position.Bottom} className="!bg-border !w-1.5 !h-1.5" />
      <div className="flex items-center gap-2 mb-1">
        <div className="flex h-5 w-5 items-center justify-center rounded bg-teal/10">
          <Icon className="h-3 w-3 text-teal" />
        </div>
        <span className="text-[10px] font-medium uppercase text-dim">{ind.type}</span>
        <Badge variant="outline" className={cn("text-[9px]", maliceColor(ind.malice))}>
          {ind.malice}
        </Badge>
      </div>
      <p className="text-[11px] font-mono text-foreground truncate max-w-[200px]">
        {ind.value}
      </p>
      <div className="flex items-center gap-2 mt-1">
        {Object.entries(ind.enrichment_summary).map(([provider, verdict]) => (
          <span key={provider} className="text-[9px] text-dim">
            {provider}: <span className="text-teal-light">{verdict}</span>
          </span>
        ))}
      </div>
      {moreCount > 0 && (
        <div className="mt-1">
          <Badge variant="outline" className="text-[9px] text-dim border-border">
            +{moreCount} more alerts
          </Badge>
        </div>
      )}
    </div>
  );
});
