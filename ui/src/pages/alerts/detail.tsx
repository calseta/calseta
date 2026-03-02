import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { JsonViewer } from "@/components/json-viewer";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
} from "@/components/detail-page";
import { CopyableText } from "@/components/copyable-text";
import {
  useAlert,
  useAlertActivity,
  useAlertContext,
  usePatchAlert,
} from "@/hooks/use-api";
import {
  formatDate,
  relativeTime,
  severityColor,
  statusColor,
  maliceColor,
  eventDotColor,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { ActorBadge } from "@/components/activity/actor-badge";
import { ActivityEventReferences } from "@/components/activity/activity-event-references";
import { AlertGraph } from "@/components/alert-graph/alert-graph";
import {
  Shield,
  Tag,
  AlertTriangle,
  CheckCircle,
  Globe,
  Hash,
  Mail,
  User,
  ExternalLink,
  Code,
  Activity,
  Zap,
  Radio,
  GitFork,
} from "lucide-react";

const SEVERITY_OPTIONS = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];

// Canonical display order — dropdown always shows statuses in this sequence.
const STATUS_ORDER = ["pending_enrichment", "enriched", "Open", "Triaging", "Escalated", "Closed"];

const STATUS_TRANSITIONS: Record<string, string[]> = {
  pending_enrichment: ["Open"],
  enriched: ["Open"],
  Open: ["Triaging", "Escalated", "Closed"],
  Triaging: ["Open", "Escalated", "Closed"],
  Escalated: ["Open", "Triaging", "Closed"],
};

const CLOSE_CLASSIFICATIONS = [
  "True Positive - Suspicious Activity",
  "Benign Positive - Suspicious but Expected",
  "False Positive - Incorrect Detection Logic",
  "False Positive - Inaccurate Data",
  "Undetermined",
  "Duplicate",
  "Not Applicable",
];

const indicatorIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  ip: Globe,
  domain: Globe,
  url: ExternalLink,
  email: Mail,
  account: User,
  hash_md5: Hash,
  hash_sha1: Hash,
  hash_sha256: Hash,
};

export function AlertDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data: alertResp, isLoading } = useAlert(uuid);
  const { data: activityResp } = useAlertActivity(uuid);
  const { data: contextResp } = useAlertContext(uuid);
  const patchAlert = usePatchAlert();

  const [closingWith, setClosingWith] = useState<string>("");
  const [showCloseFlow, setShowCloseFlow] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("indicators");

  const alert = alertResp?.data;
  const activities = activityResp?.data ?? [];
  const contextDocs = contextResp?.data ?? [];

  if (isLoading) {
    return (
      <AppLayout title="Alert">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!alert) {
    return (
      <AppLayout title="Alert">
        <div className="text-center text-dim py-20">Alert not found</div>
      </AppLayout>
    );
  }

  const nextStatuses = STATUS_TRANSITIONS[alert.status] ?? [];
  // Build the full set of selectable statuses (current + transitions) in canonical order
  const selectableStatuses = STATUS_ORDER.filter(
    (s) => s === alert.status || nextStatuses.includes(s),
  );

  function handleStatusChange(newStatus: string) {
    if (newStatus === "Closed") return; // Close requires classification — handled separately
    setPendingStatus(null);
    patchAlert.mutate(
      { uuid, body: { status: newStatus } },
      {
        onSuccess: () => toast.success(`Alert moved to ${newStatus}`),
        onError: () => toast.error("Failed to update alert status"),
      },
    );
  }

  function handleClose() {
    if (!closingWith) return;
    patchAlert.mutate(
      { uuid, body: { status: "Closed", close_classification: closingWith } },
      {
        onSuccess: () => {
          toast.success("Alert closed");
          setClosingWith("");
          setShowCloseFlow(false);
          setPendingStatus(null);
        },
        onError: () => {
          toast.error("Failed to close alert");
          setPendingStatus(null);
          setShowCloseFlow(false);
        },
      },
    );
  }

  function handleSeverityChange(newSeverity: string) {
    patchAlert.mutate(
      { uuid, body: { severity: newSeverity } },
      {
        onSuccess: () => toast.success(`Severity changed to ${newSeverity}`),
        onError: () => toast.error("Failed to update severity"),
      },
    );
  }

  // Compute dominant malice across indicators
  const maliceOrder = ["Malicious", "Suspicious", "Benign", "Pending"];
  const dominantMalice =
    alert.indicators?.reduce((worst, ind) => {
      const wi = maliceOrder.indexOf(worst);
      const ci = maliceOrder.indexOf(ind.malice);
      return ci < wi && ci >= 0 ? ind.malice : worst;
    }, "Pending") ?? "Pending";

  return (
    <AppLayout title="Alert Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/alerts"
          title={alert.title}
          badges={
            <>
              <Badge
                variant="outline"
                className={cn("text-xs", severityColor(alert.severity))}
              >
                {alert.severity}
              </Badge>
              <Badge
                variant="outline"
                className={cn("text-xs", statusColor(alert.status))}
              >
                {alert.status}
              </Badge>
              {alert.is_enriched && (
                <Badge variant="outline" className="text-xs text-teal bg-teal/10 border-teal/30">
                  Enriched
                </Badge>
              )}
            </>
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "Status",
              icon: Activity,
              value: alert.status === "Closed" ? (
                <div>
                  <Badge variant="outline" className={cn("text-xs", statusColor("Closed"))}>
                    Closed
                  </Badge>
                  {alert.close_classification && (
                    <p className="mt-1.5 text-[11px] text-dim">{alert.close_classification}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <Select
                    value={pendingStatus ?? alert.status}
                    onValueChange={(v) => {
                      if (v === "Closed") {
                        setPendingStatus("Closed");
                        setShowCloseFlow(true);
                        return;
                      }
                      setShowCloseFlow(false);
                      setClosingWith("");
                      handleStatusChange(v);
                    }}
                  >
                    <SelectTrigger className={cn("h-7 w-full text-xs border", statusColor(pendingStatus ?? alert.status))}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {selectableStatuses.map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {showCloseFlow && (
                    <div className="space-y-1.5">
                      <Select value={closingWith} onValueChange={setClosingWith}>
                        <SelectTrigger className="h-7 w-full text-xs bg-surface border-border">
                          <SelectValue placeholder="Classification..." />
                        </SelectTrigger>
                        <SelectContent className="bg-card border-border">
                          {CLOSE_CLASSIFICATIONS.map((c) => (
                            <SelectItem key={c} value={c} className="text-xs">
                              {c}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {closingWith && (
                        <Button
                          size="sm"
                          onClick={handleClose}
                          disabled={patchAlert.isPending}
                          className="h-7 w-full bg-teal text-white hover:bg-teal-dim text-xs"
                        >
                          Close Alert
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              ),
            },
            {
              label: "Severity",
              icon: AlertTriangle,
              value: (
                <Select value={alert.severity} onValueChange={handleSeverityChange}>
                  <SelectTrigger className={cn("h-7 w-full text-xs border", severityColor(alert.severity))}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    {SEVERITY_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Malice",
              icon: Zap,
              value: (
                <Badge variant="outline" className={cn("text-xs", maliceColor(dominantMalice))}>
                  {dominantMalice}
                </Badge>
              ),
            },
            {
              label: "Source",
              icon: Radio,
              value: alert.source_name,
            },
          ]}
        />

        <DetailPageLayout
          sidebar={
            <DetailPageSidebar>
              <SidebarSection title="Details">
                <DetailPageField label="UUID" value={<CopyableText text={alert.uuid} mono className="text-xs" />} />
                <DetailPageField label="Source" value={alert.source_name} />
                {alert.fingerprint && (
                  <DetailPageField label="Fingerprint" value={<CopyableText text={alert.fingerprint} mono className="text-xs" />} />
                )}
                {alert.detection_rule_id && (
                  <DetailPageField label="Detection Rule" value={`#${alert.detection_rule_id}`} />
                )}
                <DetailPageField label="Occurred At" value={formatDate(alert.occurred_at)} />
                <DetailPageField label="Ingested At" value={formatDate(alert.ingested_at)} />
                {alert.acknowledged_at && (
                  <DetailPageField label="Acknowledged" value={formatDate(alert.acknowledged_at)} />
                )}
                {alert.triaged_at && (
                  <DetailPageField label="Triaged At" value={formatDate(alert.triaged_at)} />
                )}
                {alert.closed_at && (
                  <DetailPageField label="Closed At" value={formatDate(alert.closed_at)} />
                )}
              </SidebarSection>
              {alert.tags.length > 0 && (
                <SidebarSection title="Tags">
                  <div className="flex flex-wrap gap-1.5">
                    {alert.tags.map((t) => (
                      <span
                        key={t}
                        className="flex items-center gap-1 text-[11px] text-dim bg-surface-hover px-2 py-0.5 rounded"
                      >
                        <Tag className="h-2.5 w-2.5" />
                        {t}
                      </span>
                    ))}
                  </div>
                </SidebarSection>
              )}
            </DetailPageSidebar>
          }
        >
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="bg-surface border border-border">
              <TabsTrigger value="indicators" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Indicators ({alert.indicators?.length ?? 0})
              </TabsTrigger>
              <TabsTrigger value="findings" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Findings ({alert.agent_findings?.length ?? 0})
              </TabsTrigger>
              <TabsTrigger value="context" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Context ({contextDocs.length})
              </TabsTrigger>
              <TabsTrigger value="activity" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                Activity ({activities.length})
              </TabsTrigger>
              <TabsTrigger value="graph" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <GitFork className="h-3.5 w-3.5 mr-1" />
                Graph
              </TabsTrigger>
              <TabsTrigger value="raw" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <Code className="h-3.5 w-3.5 mr-1" />
                Raw Data
              </TabsTrigger>
            </TabsList>

            {/* Indicators */}
            <TabsContent value="indicators" className="mt-4">
              {alert.indicators && alert.indicators.length > 0 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {alert.indicators.map((ind) => {
                    const Icon = indicatorIcons[ind.type] ?? Hash;
                    return (
                      <Card
                        key={ind.uuid}
                        className="bg-card border-border hover:border-teal/30 transition-colors"
                      >
                        <CardContent className="p-4">
                          <div className="flex items-start gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal/10">
                              <Icon className="h-4 w-4 text-teal" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] font-medium uppercase text-dim">
                                  {ind.type}
                                </span>
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "text-[10px]",
                                    maliceColor(ind.malice),
                                  )}
                                >
                                  {ind.malice}
                                </Badge>
                              </div>
                              <p className="mt-0.5 text-sm font-mono text-foreground break-all">
                                {ind.value}
                              </p>
                              <div className="mt-2 flex gap-3 text-[11px] text-dim">
                                <span>First: {relativeTime(ind.first_seen)}</span>
                                <span>Last: {relativeTime(ind.last_seen)}</span>
                              </div>
                              {ind.enrichment_results && (
                                <div className="mt-2 space-y-1">
                                  {Object.entries(ind.enrichment_results).map(
                                    ([provider, data]) => (
                                      <div
                                        key={provider}
                                        className="rounded bg-surface-hover p-2 text-xs"
                                      >
                                        <span className="font-medium text-teal-light">
                                          {provider}
                                        </span>
                                        <pre className="mt-1 text-[11px] text-dim whitespace-pre-wrap break-all">
                                          {JSON.stringify(data, null, 2)}
                                        </pre>
                                      </div>
                                    ),
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              ) : (
                <Empty text="No indicators extracted" />
              )}
            </TabsContent>

            {/* Findings */}
            <TabsContent value="findings" className="mt-4">
              {alert.agent_findings && alert.agent_findings.length > 0 ? (
                <div className="space-y-3">
                  {alert.agent_findings.map((f) => (
                    <Card key={f.id} className="bg-card border-border">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div>
                            <span className="text-xs font-medium text-teal-light">
                              {f.agent_name}
                            </span>
                            {f.confidence && (
                              <Badge
                                variant="outline"
                                className="ml-2 text-[10px] border-border"
                              >
                                {f.confidence} confidence
                              </Badge>
                            )}
                          </div>
                          <span className="text-[11px] text-dim">
                            {relativeTime(f.posted_at)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-foreground whitespace-pre-wrap">
                          {f.summary}
                        </p>
                        {f.recommended_action && (
                          <div className="mt-2 flex items-start gap-2 rounded bg-teal/5 p-2">
                            <CheckCircle className="h-3.5 w-3.5 mt-0.5 text-teal" />
                            <p className="text-xs text-foreground">
                              {f.recommended_action}
                            </p>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <Empty text="No agent findings yet" />
              )}
            </TabsContent>

            {/* Context Docs */}
            <TabsContent value="context" className="mt-4">
              {contextDocs.length > 0 ? (
                <div className="space-y-3">
                  {contextDocs.map((doc) => (
                    <Card key={doc.uuid} className="bg-card border-border">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-foreground">
                          {doc.title}
                        </CardTitle>
                        <span className="text-[11px] text-dim">
                          {doc.document_type}
                        </span>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <pre className="text-xs text-muted-foreground whitespace-pre-wrap max-h-48 overflow-auto">
                          {doc.content}
                        </pre>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <Empty text="No context documents apply to this alert" />
              )}
            </TabsContent>

            {/* Activity Timeline */}
            <TabsContent value="activity" className="mt-4">
              {activities.length > 0 ? (
                <div className="space-y-0">
                  {activities.map((ev, i) => (
                    <div key={ev.uuid} className="flex gap-4">
                      <div className="flex flex-col items-center">
                        <div className={cn("h-2 w-2 rounded-full mt-2", eventDotColor(ev.event_type))} />
                        {i < activities.length - 1 && (
                          <div className="w-px flex-1 bg-border" />
                        )}
                      </div>
                      <div className="pb-4">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-foreground">
                            {formatEventType(ev.event_type)}
                          </span>
                          <span className="text-[11px] text-dim">
                            {relativeTime(ev.created_at)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <ActorBadge actorType={ev.actor_type} actorKeyPrefix={ev.actor_key_prefix} />
                        </div>
                        <div className="mt-1.5">
                          <ActivityEventReferences eventType={ev.event_type} references={ev.references} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty text="No activity recorded yet" />
              )}
            </TabsContent>

            {/* Relationship Graph */}
            <TabsContent value="graph" className="mt-4">
              <AlertGraph alertUuid={uuid} />
            </TabsContent>

            {/* Raw Data */}
            <TabsContent value="raw" className="mt-4">
              {alert.raw_payload ? (
                <JsonViewer data={alert.raw_payload} defaultExpanded={2} />
              ) : (
                <Empty text="No raw payload data available" />
              )}
            </TabsContent>
          </Tabs>
        </DetailPageLayout>
      </div>
    </AppLayout>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center py-16 text-sm text-dim">
      <AlertTriangle className="h-4 w-4 mr-2" />
      {text}
    </div>
  );
}

function formatEventType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
