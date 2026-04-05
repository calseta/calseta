import { useState } from "react";
import { useParams, useSearch, useNavigate, Link } from "@tanstack/react-router";
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
import { InlineTagEditor } from "@/components/inline-tag-editor";
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
  useEnrichAlert,
} from "@/hooks/use-api";
import {
  formatDate,
  severityColor,
  statusColor,
  enrichmentStatusColor,
  maliceColor,
  eventDotColor,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { ActorBadge } from "@/components/activity/actor-badge";
import { ActivityEventReferences } from "@/components/activity/activity-event-references";
import { AddIndicatorsForm } from "@/components/add-indicators-form";
import { IndicatorDetailSheet } from "@/components/indicator-detail-sheet";
import { AlertGraph } from "@/components/alert-graph/alert-graph";
import { MarkdownPreview } from "@/components/markdown-preview";
import { RunAgentButton } from "@/components/run-agent-button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Shield,
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
  Plus,
  RefreshCw,
  FileText,
} from "lucide-react";

const SEVERITY_OPTIONS = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];
const MALICE_OPTIONS = ["Pending", "Benign", "Suspicious", "Malicious"];

// Canonical display order — dropdown always shows statuses in this sequence.
const STATUS_ORDER = ["Open", "Triaging", "Escalated", "Closed"];

const STATUS_TRANSITIONS: Record<string, string[]> = {
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
  const { tab: activeTab } = useSearch({ from: "/alerts/$uuid" });
  const navigate = useNavigate({ from: "/alerts/$uuid" });
  const { data: alertResp, isLoading, refetch, isFetching } = useAlert(uuid);
  const { data: activityResp, refetch: refetchActivity } = useAlertActivity(uuid);
  const { data: contextResp, refetch: refetchContext } = useAlertContext(uuid);
  const patchAlert = usePatchAlert();
  const enrichAlert = useEnrichAlert();

  const [closingWith, setClosingWith] = useState<string>("");
  const [showCloseFlow, setShowCloseFlow] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  function setActiveTab(tab: string) {
    navigate({ search: { tab }, replace: true });
  }
  const [showAddIndicators, setShowAddIndicators] = useState(false);
  const [selectedIndicator, setSelectedIndicator] = useState<{
    uuid: string;
    type: string;
    value: string;
    malice: string;
  } | null>(null);

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

  // Effective malice: server-returned (override > computed)
  const effectiveMalice = alert.malice ?? "Pending";
  const hasOverride = !!alert.malice_override;

  function handleMaliceChange(newMalice: string) {
    patchAlert.mutate(
      { uuid, body: { malice_override: newMalice } },
      {
        onSuccess: () => toast.success(`Alert malice set to ${newMalice}`),
        onError: () => toast.error("Failed to update malice"),
      },
    );
  }

  function handleResetMalice() {
    patchAlert.mutate(
      { uuid, body: { reset_malice_override: true } },
      {
        onSuccess: () => toast.success("Malice reset to computed value"),
        onError: () => toast.error("Failed to reset malice"),
      },
    );
  }

  return (
    <AppLayout title="Alert Detail">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/alerts"
          title={alert.title}
          subtitle={alert.description ? <p className="text-sm text-dim leading-relaxed">{alert.description}</p> : undefined}
          onRefresh={() => { refetch(); refetchActivity(); refetchContext(); }}
          isRefreshing={isFetching}
          actions={<RunAgentButton alertUuid={uuid} />}
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
              <Badge
                variant="outline"
                className={cn("text-xs", enrichmentStatusColor(alert.enrichment_status))}
              >
                {alert.enrichment_status}
              </Badge>
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
                <div className="space-y-1">
                  <Select value={effectiveMalice} onValueChange={handleMaliceChange}>
                    <SelectTrigger className={cn("h-7 w-full text-xs border", maliceColor(effectiveMalice))}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {MALICE_OPTIONS.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {hasOverride ? (
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-amber">Analyst override</span>
                      <button
                        onClick={handleResetMalice}
                        className="text-[10px] text-teal hover:underline"
                      >
                        Reset
                      </button>
                    </div>
                  ) : (
                    <span className="text-[10px] text-dim">Computed from indicators</span>
                  )}
                </div>
              ),
            },
            {
              label: "Source",
              icon: Radio,
              value: alert.source_name,
            },
          ]}
        />

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-surface border border-border">
            <TabsTrigger value="indicators" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Shield className="h-3.5 w-3.5 mr-1" />
              Indicators ({alert.indicators?.length ?? 0})
            </TabsTrigger>
            <TabsTrigger value="findings" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Zap className="h-3.5 w-3.5 mr-1" />
              Findings ({alert.agent_findings?.length ?? 0})
            </TabsTrigger>
            <TabsTrigger value="context" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Context ({contextDocs.length})
            </TabsTrigger>
            <TabsTrigger value="activity" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Activity className="h-3.5 w-3.5 mr-1" />
              Activity ({activities.length})
            </TabsTrigger>
            <TabsTrigger value="ads" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              ADS
            </TabsTrigger>
            <TabsTrigger value="graph" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <GitFork className="h-3.5 w-3.5 mr-1" />
              Graph
            </TabsTrigger>
            <TabsTrigger value="agent-payload" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Zap className="h-3.5 w-3.5 mr-1" />
              Agent Payload
            </TabsTrigger>
            <TabsTrigger value="raw" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <Code className="h-3.5 w-3.5 mr-1" />
              Raw Data
            </TabsTrigger>
          </TabsList>

          <DetailPageLayout
            sidebar={
              <DetailPageSidebar>
                <SidebarSection title="Details">
                  <DetailPageField label="UUID" value={<CopyableText text={alert.uuid} mono className="text-xs" />} />
                <DetailPageField label="Source" value={alert.source_name} />
                {alert.fingerprint && (
                  <DetailPageField label="Fingerprint" value={<CopyableText text={alert.fingerprint} mono className="text-xs" />} />
                )}

                {alert.duplicate_count > 0 && (
                  <DetailPageField label="Duplicates" value={alert.duplicate_count} />
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
              <SidebarSection title="Tags">
                <InlineTagEditor
                  tags={alert.tags}
                  disabled={patchAlert.isPending}
                  onSave={(newTags) =>
                    patchAlert.mutate(
                      { uuid, body: { tags: newTags } },
                      { onSuccess: () => toast.success("Tags updated") },
                    )
                  }
                />
              </SidebarSection>
              {alert.detection_rule && (
                <SidebarSection title="Detection Rule">
                  <DetailPageField
                    label="Name"
                    value={
                      <Link
                        to="/manage/detection-rules/$uuid"
                        params={{ uuid: alert.detection_rule.uuid }}
                        search={{ tab: "documentation" }}
                        className="text-teal hover:underline text-xs truncate max-w-[160px] inline-block"
                      >
                        {alert.detection_rule.name}
                      </Link>
                    }
                  />
                  <DetailPageField label="Rule ID" value={alert.detection_rule.source_rule_id ? <CopyableText text={alert.detection_rule.source_rule_id} mono className="text-xs" /> : "—"} />
                  <DetailPageField
                    label="Status"
                    value={
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px]",
                          alert.detection_rule.is_active
                            ? "text-teal bg-teal/10 border-teal/30"
                            : "text-dim bg-dim/10 border-dim/30",
                        )}
                      >
                        {alert.detection_rule.is_active ? "active" : "inactive"}
                      </Badge>
                    }
                  />
                  {alert.detection_rule.severity && (
                    <DetailPageField
                      label="Severity"
                      value={
                        <Badge variant="outline" className={cn("text-[10px]", severityColor(alert.detection_rule.severity))}>
                          {alert.detection_rule.severity}
                        </Badge>
                      }
                    />
                  )}
                  <DetailPageField label="Source" value={alert.detection_rule.source_name ?? "—"} />
                </SidebarSection>
              )}
            </DetailPageSidebar>
          }
        >
            {/* Indicators */}
            <TabsContent value="indicators" className="mt-4">
              <div className="space-y-4">
                {!showAddIndicators && (
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        enrichAlert.mutate(uuid, {
                          onSuccess: () =>
                            toast.success(
                              "Enrichment queued — results will appear shortly",
                            ),
                          onError: () =>
                            toast.error("Failed to queue enrichment"),
                        });
                      }}
                      disabled={enrichAlert.isPending}
                      className="h-7 text-xs text-teal border-teal/30 hover:bg-teal/10"
                    >
                      <RefreshCw
                        className={cn(
                          "h-3.5 w-3.5 mr-1",
                          enrichAlert.isPending && "animate-spin",
                        )}
                      />
                      Re-enrich
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowAddIndicators(true)}
                      className="h-7 text-xs text-teal border-teal/30 hover:bg-teal/10"
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      Add Indicators
                    </Button>
                  </div>
                )}

                {showAddIndicators && (
                  <AddIndicatorsForm
                    alertUuid={uuid}
                    onDone={() => setShowAddIndicators(false)}
                  />
                )}

                {alert.indicators && alert.indicators.length > 0 ? (
                  <div className="rounded-lg border border-border overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                          <TableHead className="text-xs text-dim">Type</TableHead>
                          <TableHead className="text-xs text-dim">Value</TableHead>
                          <TableHead className="text-xs text-dim">Malice</TableHead>
                          <TableHead className="text-xs text-dim">Enrichments</TableHead>
                          <TableHead className="text-xs text-dim">First Seen</TableHead>
                          <TableHead className="text-xs text-dim">Last Seen</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {alert.indicators.map((ind) => {
                          const Icon = indicatorIcons[ind.type] ?? Hash;
                          const enrichmentCount = ind.enrichment_results
                            ? Object.keys(ind.enrichment_results).length
                            : 0;
                          return (
                            <TableRow
                              key={ind.uuid}
                              className="border-border cursor-pointer hover:bg-surface-hover"
                              onClick={() =>
                                setSelectedIndicator({
                                  uuid: ind.uuid,
                                  type: ind.type,
                                  value: ind.value,
                                  malice: ind.malice,
                                })
                              }
                            >
                              <TableCell>
                                <div className="flex items-center gap-1.5">
                                  <Icon className="h-3.5 w-3.5 text-teal" />
                                  <span className="text-[11px] font-semibold uppercase text-dim">
                                    {ind.type}
                                  </span>
                                </div>
                              </TableCell>
                              <TableCell className="font-mono text-xs max-w-[260px] truncate">
                                {ind.value}
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant="outline"
                                  className={cn("text-[10px]", maliceColor(ind.malice))}
                                >
                                  {ind.malice}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs text-dim">
                                {enrichmentCount > 0 ? enrichmentCount : "—"}
                              </TableCell>
                              <TableCell className="text-xs text-dim">
                                {formatDate(ind.first_seen)}
                              </TableCell>
                              <TableCell className="text-xs text-dim">
                                {formatDate(ind.last_seen)}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  !showAddIndicators && <Empty text="No indicators extracted" />
                )}

                <IndicatorDetailSheet
                  indicator={selectedIndicator}
                  alertUuid={uuid}
                  onClose={() => setSelectedIndicator(null)}
                />
              </div>
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
                            <Link
                              to="/manage/agents"
                              className="text-xs font-medium text-teal-light hover:underline"
                            >
                              {f.agent_name}
                            </Link>
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
                            {formatDate(f.posted_at)}
                          </span>
                        </div>
                        <div className="mt-2 text-foreground">
                          <MarkdownPreview content={f.summary} />
                        </div>
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
                            {formatDate(ev.created_at)}
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

            {/* ADS — Detection Rule Documentation */}
            <TabsContent value="ads" className="mt-4">
              {alert.detection_rule?.documentation ? (
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium text-foreground">
                        Alerting and Detection Strategy
                      </CardTitle>
                      <Link
                        to="/manage/detection-rules/$uuid"
                        params={{ uuid: alert.detection_rule.uuid }}
                        search={{ tab: "documentation" }}
                        className="text-xs text-teal hover:underline"
                      >
                        View Rule
                      </Link>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <MarkdownPreview content={alert.detection_rule.documentation} />
                  </CardContent>
                </Card>
              ) : (
                <Empty text={alert.detection_rule ? "No ADS documentation for this detection rule" : "No detection rule linked to this alert"} />
              )}
            </TabsContent>

            {/* Relationship Graph */}
            <TabsContent value="graph" className="mt-4">
              <AlertGraph alertUuid={uuid} />
            </TabsContent>

            {/* Agent Payload */}
            <TabsContent value="agent-payload" className="mt-4">
              <div className="space-y-3">
                <p className="text-xs text-dim">
                  This is the exact JSON payload an agent receives via{" "}
                  <code className="text-teal">GET /v1/alerts/{uuid}</code>{" "}
                  or MCP resource{" "}
                  <code className="text-teal">calseta://alerts/{uuid}</code>.
                </p>
                <JsonViewer data={alertResp} defaultExpanded={Infinity} />
              </div>
            </TabsContent>

            {/* Raw Data */}
            <TabsContent value="raw" className="mt-4">
              {alert.raw_payload ? (
                <JsonViewer data={alert.raw_payload} defaultExpanded={2} />
              ) : (
                <Empty text="No raw payload data available" />
              )}
            </TabsContent>
        </DetailPageLayout>
        </Tabs>
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
