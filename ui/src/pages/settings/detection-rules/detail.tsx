import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DocumentationEditor,
} from "@/components/detail-page";
import { useDetectionRule, usePatchDetectionRule } from "@/hooks/use-api";
import { formatDate, severityColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Shield, AlertTriangle, Radio } from "lucide-react";

export function DetectionRuleDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { data, isLoading } = useDetectionRule(uuid);
  const patchRule = usePatchDetectionRule();

  const rule = data?.data;

  if (isLoading) {
    return (
      <AppLayout title="Detection Rule">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!rule) {
    return (
      <AppLayout title="Detection Rule">
        <div className="text-center text-dim py-20">Detection rule not found</div>
      </AppLayout>
    );
  }

  function handleSaveDoc(content: string) {
    patchRule.mutate(
      { uuid, body: { documentation: content } },
      {
        onSuccess: () => toast.success("Documentation saved"),
        onError: () => toast.error("Failed to save documentation"),
      },
    );
  }

  return (
    <AppLayout title="Detection Rule">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/settings/detection-rules"
          title={rule.name}
          subtitle={
            <div className="flex flex-wrap gap-3 text-xs text-dim">
              {rule.source_rule_id && <span>Rule ID: {rule.source_rule_id}</span>}
              {rule.run_frequency && <span>Frequency: {rule.run_frequency}</span>}
              {rule.created_by && <span>By: {rule.created_by}</span>}
              <span>Created: {formatDate(rule.created_at)}</span>
              <span>Updated: {formatDate(rule.updated_at)}</span>
            </div>
          }
          badges={
            <>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs",
                  rule.is_active
                    ? "text-teal bg-teal/10 border-teal/30"
                    : "text-dim bg-dim/10 border-dim/30",
                )}
              >
                {rule.is_active ? "active" : "inactive"}
              </Badge>
              {rule.severity && (
                <Badge variant="outline" className={cn("text-xs", severityColor(rule.severity))}>
                  {rule.severity}
                </Badge>
              )}
            </>
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "Status",
              icon: Shield,
              value: (
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    rule.is_active
                      ? "text-teal bg-teal/10 border-teal/30"
                      : "text-dim bg-dim/10 border-dim/30",
                  )}
                >
                  {rule.is_active ? "active" : "inactive"}
                </Badge>
              ),
            },
            {
              label: "Severity",
              icon: AlertTriangle,
              value: rule.severity ? (
                <Badge variant="outline" className={cn("text-xs", severityColor(rule.severity))}>
                  {rule.severity}
                </Badge>
              ) : (
                <span className="text-dim">—</span>
              ),
            },
            {
              label: "Source",
              icon: Radio,
              value: rule.source_name ?? "—",
            },
          ]}
        />

        {/* Metadata cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs text-dim">MITRE ATT&CK</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {rule.mitre_tactics?.length > 0 && (
                  <div>
                    <span className="text-[11px] text-dim">Tactics:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {rule.mitre_tactics.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-teal bg-teal/10 border-teal/30">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {rule.mitre_techniques?.length > 0 && (
                  <div>
                    <span className="text-[11px] text-dim">Techniques:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {rule.mitre_techniques.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {rule.mitre_subtechniques?.length > 0 && (
                  <div>
                    <span className="text-[11px] text-dim">Sub-techniques:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {rule.mitre_subtechniques.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {!rule.mitre_tactics?.length && !rule.mitre_techniques?.length && (
                  <span className="text-xs text-dim">No MITRE mappings</span>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs text-dim">Data Sources</CardTitle>
            </CardHeader>
            <CardContent>
              {rule.data_sources?.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {rule.data_sources.map((ds) => (
                    <Badge key={ds} variant="outline" className="text-[11px] text-foreground border-border">
                      {ds}
                    </Badge>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-dim">No data sources specified</span>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs text-dim">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              {rule.run_frequency && <div>Frequency: {rule.run_frequency}</div>}
              {rule.created_by && <div>Created by: {rule.created_by}</div>}
              {rule.source_rule_id && <div>Rule ID: {rule.source_rule_id}</div>}
            </CardContent>
          </Card>
        </div>

        <DocumentationEditor
          content={rule.documentation ?? ""}
          onSave={handleSaveDoc}
          isSaving={patchRule.isPending}
        />
      </div>
    </AppLayout>
  );
}
