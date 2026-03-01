import { Badge } from "@/components/ui/badge";
import { severityColor, statusColor, maliceColor } from "@/lib/format";
import { Shield, ArrowRight } from "lucide-react";

interface ActivityEventReferencesProps {
  eventType: string;
  references: Record<string, unknown> | null;
}

export function ActivityEventReferences({ eventType, references }: ActivityEventReferencesProps) {
  if (!references || Object.keys(references).length === 0) return null;

  const r = references;

  switch (eventType) {
    case "alert_ingested":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <Shield className="h-3 w-3 text-teal shrink-0" />
          {r.source_name && <span className="text-xs text-foreground">{String(r.source_name)}</span>}
          {r.indicator_count != null && (
            <Badge variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
              {String(r.indicator_count)} indicators
            </Badge>
          )}
        </div>
      );

    case "alert_enrichment_completed":
      return (
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            {r.indicator_count != null && (
              <span className="text-xs text-foreground">
                {String(r.indicator_count)} indicators enriched
              </span>
            )}
            {Array.isArray(r.providers_succeeded) && r.providers_succeeded.map((p) => (
              <Badge key={String(p)} variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
                {String(p)}
              </Badge>
            ))}
            {Array.isArray(r.providers_failed) && r.providers_failed.map((p) => (
              <Badge key={String(p)} variant="outline" className="text-[10px] text-red-threat bg-red-threat/10 border-red-threat/30">
                {String(p)}
              </Badge>
            ))}
          </div>
          {r.malice_counts && typeof r.malice_counts === "object" && (
            <div className="flex items-center gap-1.5 flex-wrap">
              {Object.entries(r.malice_counts as Record<string, number>).map(([malice, count]) => (
                <Badge key={malice} variant="outline" className={`text-[10px] ${maliceColor(malice)}`}>
                  {malice}: {count}
                </Badge>
              ))}
            </div>
          )}
        </div>
      );

    case "alert_status_updated":
      return (
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className={`text-[10px] ${statusColor(String(r.from_status ?? ""))}`}>
            {String(r.from_status ?? "")}
          </Badge>
          <ArrowRight className="h-3 w-3 text-dim" />
          <Badge variant="outline" className={`text-[10px] ${statusColor(String(r.to_status ?? ""))}`}>
            {String(r.to_status ?? "")}
          </Badge>
        </div>
      );

    case "alert_severity_updated":
      return (
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className={`text-[10px] ${severityColor(String(r.from_severity ?? ""))}`}>
            {String(r.from_severity ?? "")}
          </Badge>
          <ArrowRight className="h-3 w-3 text-dim" />
          <Badge variant="outline" className={`text-[10px] ${severityColor(String(r.to_severity ?? ""))}`}>
            {String(r.to_severity ?? "")}
          </Badge>
        </div>
      );

    case "alert_closed":
      return (
        <div className="flex items-center gap-2">
          {r.close_classification && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.close_classification)}
            </Badge>
          )}
        </div>
      );

    case "alert_finding_added":
      return (
        <div className="flex items-center gap-2">
          {r.agent_name && (
            <span className="text-xs text-teal">{String(r.agent_name)}</span>
          )}
          {r.finding_id && (
            <span className="text-[10px] text-dim font-mono">{String(r.finding_id).slice(0, 8)}</span>
          )}
        </div>
      );

    case "alert_workflow_triggered":
      return (
        <div className="flex items-center gap-2">
          {r.workflow_name && (
            <span className="text-xs text-foreground">{String(r.workflow_name)}</span>
          )}
          {r.trigger_type && (
            <Badge variant="outline" className="text-[10px] text-dim border-border">
              {String(r.trigger_type)}
            </Badge>
          )}
        </div>
      );

    case "workflow_executed":
      return (
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={`text-[10px] ${
              r.status === "success" || r.success === true
                ? "text-teal bg-teal/10 border-teal/30"
                : "text-red-threat bg-red-threat/10 border-red-threat/30"
            }`}
          >
            {r.status === "success" || r.success === true ? "Success" : "Failed"}
          </Badge>
          {r.duration_ms != null && (
            <span className="text-[10px] text-dim">{String(r.duration_ms)}ms</span>
          )}
          {r.run_uuid && (
            <span className="text-[10px] text-dim font-mono">{String(r.run_uuid).slice(0, 8)}</span>
          )}
        </div>
      );

    case "workflow_approval_requested":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          {r.confidence != null && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.confidence)} confidence
            </Badge>
          )}
          {r.run_uuid && (
            <span className="text-[10px] text-dim font-mono">{String(r.run_uuid).slice(0, 8)}</span>
          )}
          {r.reason && (
            <span className="text-[11px] text-dim italic truncate max-w-64">
              {String(r.reason)}
            </span>
          )}
        </div>
      );

    case "workflow_approval_responded":
      return (
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={`text-[10px] ${
              r.decision === "approved"
                ? "text-teal bg-teal/10 border-teal/30"
                : "text-red-threat bg-red-threat/10 border-red-threat/30"
            }`}
          >
            {r.decision === "approved" ? "Approved" : "Rejected"}
          </Badge>
          {r.responder_id && (
            <span className="text-[10px] text-dim font-mono">{String(r.responder_id)}</span>
          )}
        </div>
      );

    case "detection_rule_created":
      return (
        <div className="flex items-center gap-2">
          <Shield className="h-3 w-3 text-teal shrink-0" />
          {r.source_name && <span className="text-xs text-foreground">{String(r.source_name)}</span>}
          {r.rule_id && <span className="text-[10px] text-dim font-mono">{String(r.rule_id)}</span>}
        </div>
      );

    case "detection_rule_updated":
      return (
        <div className="flex items-center gap-1.5 flex-wrap">
          {Array.isArray(r.changed_fields) &&
            r.changed_fields.map((f) => (
              <Badge key={String(f)} variant="outline" className="text-[10px] text-dim font-mono border-border">
                {String(f)}
              </Badge>
            ))}
        </div>
      );

    default:
      return (
        <div className="text-[11px] text-dim font-mono">
          {JSON.stringify(references)}
        </div>
      );
  }
}
