import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { severityColor, statusColor, maliceColor } from "@/lib/format";
import { Shield, ArrowRight, Zap } from "lucide-react";

interface ActivityEventReferencesProps {
  eventType: string;
  references: Record<string, unknown> | null;
}

function WorkflowLink({ name, uuid }: { name?: string; uuid?: string }) {
  if (!name) return null;
  if (uuid) {
    return (
      <Link
        to="/workflows/$uuid"
        params={{ uuid: String(uuid) }}
        search={{ tab: undefined }}
        className="text-xs text-teal hover:underline"
      >
        {String(name)}
      </Link>
    );
  }
  return <span className="text-xs text-foreground">{String(name)}</span>;
}

function IndicatorBadge({ type, value }: { type?: unknown; value?: unknown }) {
  if (!type || !value) return null;
  const v = String(value);
  return (
    <Badge variant="outline" className="text-[10px] text-dim font-mono border-border max-w-48 truncate">
      {String(type)}: {v.length > 30 ? v.slice(0, 30) + "..." : v}
    </Badge>
  );
}

export function ActivityEventReferences({ eventType, references }: ActivityEventReferencesProps) {
  if (!references || Object.keys(references).length === 0) return null;

  const r = references;

  switch (eventType) {
    case "alert_ingested":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <Shield className="h-3 w-3 text-teal shrink-0" />
          {r.source_name != null && <span className="text-xs text-foreground">{String(r.source_name)}</span>}
          {r.severity != null && (
            <Badge variant="outline" className={`text-[10px] ${severityColor(String(r.severity))}`}>
              {String(r.severity)}
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
          {r.malice_counts != null && typeof r.malice_counts === "object" && (
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
          {r.close_classification != null && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.close_classification)}
            </Badge>
          )}
        </div>
      );

    case "alert_finding_added":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          {r.agent_name != null && (
            <span className="text-xs text-teal">{String(r.agent_name)}</span>
          )}
          {r.confidence != null && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.confidence)} confidence
            </Badge>
          )}
          {r.finding_id != null && (
            <span className="text-[10px] text-dim font-mono">{String(r.finding_id).slice(0, 8)}</span>
          )}
          {r.summary != null && (
            <span className="text-[11px] text-dim italic truncate max-w-72">
              {String(r.summary)}
            </span>
          )}
        </div>
      );

    case "alert_indicators_added":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          {r.indicator_count != null && (
            <span className="text-xs text-foreground">
              {String(r.indicator_count)} indicator{Number(r.indicator_count) !== 1 ? "s" : ""} added
            </span>
          )}
          {r.enrich_requested === true && (
            <Badge variant="outline" className="text-[10px] text-teal bg-teal/10 border-teal/30">
              enrichment queued
            </Badge>
          )}
          {Array.isArray(r.indicators) &&
            (r.indicators as { type: string; value: string }[]).map((ind, i) => (
              <Badge
                key={i}
                variant="outline"
                className="text-[10px] text-dim font-mono border-border max-w-48 truncate"
              >
                {ind.type}: {ind.value.length > 30 ? ind.value.slice(0, 30) + "..." : ind.value}
              </Badge>
            ))}
        </div>
      );

    case "alert_workflow_triggered":
      return (
        <div className="flex items-center gap-2">
          {r.workflow_name != null && (
            <span className="text-xs text-foreground">{String(r.workflow_name)}</span>
          )}
          {r.trigger_type != null && (
            <Badge variant="outline" className="text-[10px] text-dim border-border">
              {String(r.trigger_type)}
            </Badge>
          )}
        </div>
      );

    case "workflow_executed":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <WorkflowLink name={r.workflow_name as string} uuid={r.workflow_uuid as string} />
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
          {r.trigger_type != null && (
            <Badge variant="outline" className="text-[10px] text-dim border-border">
              {String(r.trigger_type)}
            </Badge>
          )}
          <IndicatorBadge type={r.indicator_type} value={r.indicator_value} />
          {r.approval_uuid != null && (
            <Badge variant="outline" className="text-[10px] text-amber bg-amber/10 border-amber/30">
              via approval
            </Badge>
          )}
          {r.duration_ms != null && (
            <span className="text-[10px] text-dim">{String(r.duration_ms)}ms</span>
          )}
          {r.run_uuid != null && (
            <span className="text-[10px] text-dim font-mono">{String(r.run_uuid).slice(0, 8)}</span>
          )}
        </div>
      );

    case "workflow_approval_requested":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <WorkflowLink name={r.workflow_name as string} uuid={r.workflow_uuid as string} />
          {r.trigger_source != null && (
            <Badge variant="outline" className="text-[10px] text-dim border-border">
              {String(r.trigger_source)}
            </Badge>
          )}
          <IndicatorBadge type={r.indicator_type} value={r.indicator_value} />
          {r.confidence != null && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.confidence)} confidence
            </Badge>
          )}
          {r.approval_uuid != null && (
            <span className="text-[10px] text-dim font-mono">{String(r.approval_uuid).slice(0, 8)}</span>
          )}
          {r.reason != null && (
            <span className="text-[11px] text-dim italic truncate max-w-64">
              {String(r.reason)}
            </span>
          )}
        </div>
      );

    case "workflow_approval_responded":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <WorkflowLink name={r.workflow_name as string} uuid={r.workflow_uuid as string} />
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
          <IndicatorBadge type={r.indicator_type} value={r.indicator_value} />
          {r.actor_key_prefix != null && (
            <span className="text-[10px] text-dim">
              by{" "}
              <span className="font-mono">{String(r.actor_key_prefix)}...</span>
              {r.actor_key_name != null && (
                <span className="text-foreground ml-1">({String(r.actor_key_name)})</span>
              )}
            </span>
          )}
          {r.actor_key_prefix == null && r.responder_id != null && (
            <span className="text-[10px] text-dim font-mono">{String(r.responder_id)}</span>
          )}
        </div>
      );

    case "alert_deduplicated":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          {r.duplicate_count != null && (
            <Badge variant="outline" className="text-[10px] text-foreground border-border">
              {String(r.duplicate_count)} duplicates
            </Badge>
          )}
          {r.source_name != null && (
            <span className="text-xs text-dim">{String(r.source_name)}</span>
          )}
          {r.fingerprint != null && (
            <span className="text-[10px] text-dim font-mono">
              {String(r.fingerprint).length > 16
                ? String(r.fingerprint).slice(0, 16) + "..."
                : String(r.fingerprint)}
            </span>
          )}
        </div>
      );

    case "agent_webhook_dispatched":
      return (
        <div className="flex items-center gap-2 flex-wrap">
          {r.agent_name != null && (
            <span className="text-xs text-foreground">{String(r.agent_name)}</span>
          )}
          <Badge
            variant="outline"
            className={`text-[10px] ${
              r.delivered === true
                ? "text-teal bg-teal/10 border-teal/30"
                : "text-red-threat bg-red-threat/10 border-red-threat/30"
            }`}
          >
            {r.delivered === true ? "Delivered" : "Failed"}
          </Badge>
          {r.status_code != null && (
            <span className="text-[10px] text-dim font-mono">HTTP {String(r.status_code)}</span>
          )}
        </div>
      );

    case "detection_rule_created":
      return (
        <div className="flex items-center gap-2">
          <Shield className="h-3 w-3 text-teal shrink-0" />
          {r.source_name != null && <span className="text-xs text-foreground">{String(r.source_name)}</span>}
          {r.rule_id != null && <span className="text-[10px] text-dim font-mono">{String(r.rule_id)}</span>}
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

    case "indicator_malice_updated":
      return (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Zap className="h-3 w-3 text-amber shrink-0" />
          {r.indicator_type != null && r.indicator_value != null && (
            <span className="text-xs text-dim font-mono">
              {String(r.indicator_type)}: {String(r.indicator_value).length > 30
                ? String(r.indicator_value).slice(0, 30) + "..."
                : String(r.indicator_value)}
            </span>
          )}
          {r.from_malice != null && (
            <Badge variant="outline" className={`text-[10px] ${maliceColor(String(r.from_malice))}`}>
              {String(r.from_malice)}
            </Badge>
          )}
          <ArrowRight className="h-3 w-3 text-dim" />
          <Badge variant="outline" className={`text-[10px] ${maliceColor(String(r.to_malice ?? "Pending"))}`}>
            {String(r.to_malice ?? "enrichment")}
          </Badge>
          {r.malice_source != null && (
            <span className="text-[10px] text-dim">({String(r.malice_source)})</span>
          )}
        </div>
      );

    case "alert_malice_updated":
      return (
        <div className="flex items-center gap-1.5">
          <Zap className="h-3 w-3 text-amber shrink-0" />
          {r.from_malice != null && (
            <Badge variant="outline" className={`text-[10px] ${maliceColor(String(r.from_malice))}`}>
              {String(r.from_malice)}
            </Badge>
          )}
          <ArrowRight className="h-3 w-3 text-dim" />
          {r.to_malice != null ? (
            <Badge variant="outline" className={`text-[10px] ${maliceColor(String(r.to_malice))}`}>
              {String(r.to_malice)}
            </Badge>
          ) : (
            <span className="text-[10px] text-dim">reset to computed</span>
          )}
          {r.malice_source != null && (
            <span className="text-[10px] text-dim">({String(r.malice_source)})</span>
          )}
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
