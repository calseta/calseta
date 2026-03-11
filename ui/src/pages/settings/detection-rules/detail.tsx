import { useState } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DetailPageLayout,
  DetailPageSidebar,
  SidebarSection,
  DetailPageField,
  DocumentationEditor,
} from "@/components/detail-page";
import { CopyableText } from "@/components/copyable-text";
import { useDetectionRule, usePatchDetectionRule } from "@/hooks/use-api";
import { formatDate, severityColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Shield, AlertTriangle, Radio, FileText, Settings, Save, Loader2, X, Plus } from "lucide-react";
import type { DetectionRule } from "@/lib/types";

const SEVERITY_OPTIONS = ["Pending", "Informational", "Low", "Medium", "High", "Critical"];

function buildDocumentationTemplate(rule: DetectionRule): string {
  const name = rule.name || "Rule Name";
  const enabled = rule.is_active ? "yes" : "no";
  const createdBy = rule.created_by || "";
  const frequency = rule.run_frequency || "";
  const severity = rule.severity?.toLowerCase() || "";
  const tactics = rule.mitre_tactics?.length
    ? rule.mitre_tactics.join(", ")
    : "";
  const techniques = rule.mitre_techniques?.length
    ? rule.mitre_techniques.join(", ")
    : "";
  const subtechniques = rule.mitre_subtechniques?.length
    ? rule.mitre_subtechniques.join(", ")
    : "";
  const dataSources = rule.data_sources?.length
    ? rule.data_sources.map((ds) => `* \`${ds}\``).join("\n")
    : "* ";
  const ruleId = rule.source_rule_id || "";

  return `# ${name}

## Overview

>

---

## Metadata

* **ID:** \`${ruleId}\`
* **Enabled:** \`${enabled}\`
* **Created By:** \`${createdBy}\`
* **Runs Every:** \`${frequency}\`
* **Severity:** \`${severity}\`

---

## Query

\`\`\`
\`\`\`

---

## Threshold *(optional)*

* **Field:** \`\`
* **Threshold:** \`\`

---

## Alert Suppression *(optional)*

* **Suppression Field:** \`\`
* **Suppression Duration:** \`\`

---

## Machine Learning Job *(optional)*

>

---

## MITRE ATT&CK

* **Tactics:** \`${tactics}\`
* **Techniques:** \`${techniques}\`
* **Sub-Techniques:** \`${subtechniques}\`

---

## Goal

>

---

## Strategy Abstract

>

---

## Data Sources

${dataSources}

---

## Blind Spots & Assumptions

*

---

## False Positives

*

---

## Validation

>

---

## Priority

>

---

## Responses

*

---

## Additional Notes

*
`;
}

export function DetectionRuleDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { tab: activeTab } = useSearch({ from: "/manage/detection-rules/$uuid" });
  const navigate = useNavigate();
  const { data, isLoading, refetch, isFetching } = useDetectionRule(uuid);
  const patchRule = usePatchDetectionRule();

  const rule = data?.data;

  const [editOpen, setEditOpen] = useState(false);
  const [editDraft, setEditDraft] = useState<Record<string, unknown>>({});
  const [newTactic, setNewTactic] = useState("");
  const [newTechnique, setNewTechnique] = useState("");
  const [newSubtechnique, setNewSubtechnique] = useState("");
  const [newDataSource, setNewDataSource] = useState("");

  function setActiveTab(tab: string) {
    navigate({ search: { tab }, replace: true });
  }

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

  function handleStatusChange(isActive: boolean) {
    patchRule.mutate(
      { uuid, body: { is_active: isActive } },
      {
        onSuccess: () => toast.success(`Rule ${isActive ? "activated" : "deactivated"}`),
        onError: () => toast.error("Failed to update status"),
      },
    );
  }

  function handleSeverityChange(severity: string) {
    patchRule.mutate(
      { uuid, body: { severity } },
      {
        onSuccess: () => toast.success(`Severity changed to ${severity}`),
        onError: () => toast.error("Failed to update severity"),
      },
    );
  }

  function openEditDialog() {
    if (!rule) return;
    setEditDraft({
      name: rule.name,
      severity: rule.severity ?? "Pending",
      is_active: rule.is_active,
      mitre_tactics: [...(rule.mitre_tactics ?? [])],
      mitre_techniques: [...(rule.mitre_techniques ?? [])],
      mitre_subtechniques: [...(rule.mitre_subtechniques ?? [])],
      data_sources: [...(rule.data_sources ?? [])],
    });
    setNewTactic("");
    setNewTechnique("");
    setNewSubtechnique("");
    setNewDataSource("");
    setEditOpen(true);
  }

  function updateDraft(key: string, value: unknown) {
    setEditDraft((prev) => ({ ...prev, [key]: value }));
  }

  function addToList(key: string, value: string, resetFn: (v: string) => void) {
    const trimmed = value.trim();
    if (!trimmed) return;
    const list = (editDraft[key] as string[]) ?? [];
    if (!list.includes(trimmed)) {
      updateDraft(key, [...list, trimmed]);
    }
    resetFn("");
  }

  function removeFromList(key: string, value: string) {
    const list = (editDraft[key] as string[]) ?? [];
    updateDraft(key, list.filter((v) => v !== value));
  }

  function handleSaveEdit() {
    patchRule.mutate(
      { uuid, body: { ...editDraft } },
      {
        onSuccess: () => {
          toast.success("Detection rule updated");
          setEditOpen(false);
        },
        onError: () => toast.error("Failed to update detection rule"),
      },
    );
  }

  return (
    <AppLayout title="Detection Rule">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/detection-rules"
          title={rule.name}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          subtitle={
            <div className="flex flex-wrap gap-3 text-xs text-dim">
              {rule.source_rule_id && <span>Rule ID: {rule.source_rule_id}</span>}
              {rule.run_frequency && <span>Frequency: {rule.run_frequency}</span>}
              {rule.created_by && <span>By: {rule.created_by}</span>}
              <span>Created: {formatDate(rule.created_at)}</span>
              <span>Updated: {formatDate(rule.updated_at)}</span>
            </div>
          }
          actions={
            <Button
              size="sm"
              variant="outline"
              onClick={openEditDialog}
              className="border-border text-xs"
            >
              <Settings className="h-3 w-3 mr-1" />
              Edit Rule
            </Button>
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
                <Select
                  value={rule.is_active ? "active" : "inactive"}
                  onValueChange={(v) => handleStatusChange(v === "active")}
                >
                  <SelectTrigger className={cn(
                    "h-7 w-full text-xs border",
                    rule.is_active
                      ? "text-teal bg-teal/10 border-teal/30"
                      : "text-dim bg-dim/10 border-dim/30",
                  )}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Severity",
              icon: AlertTriangle,
              value: (
                <Select value={rule.severity ?? "Pending"} onValueChange={handleSeverityChange}>
                  <SelectTrigger className={cn("h-7 w-full text-xs border", severityColor(rule.severity ?? "Pending"))}>
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
              label: "Source",
              icon: Radio,
              value: rule.source_name ?? "—",
            },
          ]}
        />

        <DetailPageLayout
          sidebar={
            <DetailPageSidebar>
              <SidebarSection title="Details">
                <DetailPageField label="UUID" value={<CopyableText text={rule.uuid} mono className="text-xs" />} />
                {rule.source_rule_id && (
                  <DetailPageField label="Rule ID" value={<CopyableText text={rule.source_rule_id} mono className="text-xs" />} />
                )}
                <DetailPageField label="Source" value={rule.source_name ?? "—"} />
                {rule.run_frequency && (
                  <DetailPageField label="Frequency" value={rule.run_frequency} />
                )}
                {rule.created_by && (
                  <DetailPageField label="Created By" value={rule.created_by} />
                )}
                <DetailPageField label="Created" value={formatDate(rule.created_at)} />
                <DetailPageField label="Updated" value={formatDate(rule.updated_at)} />
              </SidebarSection>

              {(rule.mitre_tactics?.length > 0 || rule.mitre_techniques?.length > 0 || rule.mitre_subtechniques?.length > 0) && (
                <SidebarSection title="MITRE ATT&CK">
                  {rule.mitre_tactics?.length > 0 && (
                    <div>
                      <span className="text-[11px] text-dim">Tactics</span>
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
                      <span className="text-[11px] text-dim">Techniques</span>
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
                      <span className="text-[11px] text-dim">Sub-techniques</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {rule.mitre_subtechniques.map((t) => (
                          <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </SidebarSection>
              )}

              {rule.data_sources?.length > 0 && (
                <SidebarSection title="Data Sources">
                  <div className="flex flex-wrap gap-1">
                    {rule.data_sources.map((ds) => (
                      <Badge key={ds} variant="outline" className="text-[11px] text-foreground border-border">
                        {ds}
                      </Badge>
                    ))}
                  </div>
                </SidebarSection>
              )}
            </DetailPageSidebar>
          }
        >
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="bg-surface border border-border">
              <TabsTrigger value="documentation" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <FileText className="h-3.5 w-3.5 mr-1" />
                Documentation
              </TabsTrigger>
            </TabsList>

            <TabsContent value="documentation" className="mt-4">
              <DocumentationEditor
                content={rule.documentation ?? ""}
                onSave={handleSaveDoc}
                isSaving={patchRule.isPending}
                templateContent={buildDocumentationTemplate(rule)}
              />
            </TabsContent>
          </Tabs>
        </DetailPageLayout>
      </div>

      {/* Edit Detection Rule Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">Edit Detection Rule</DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            {/* Name */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Name</Label>
              <Input
                value={(editDraft.name as string) ?? ""}
                onChange={(e) => updateDraft("name", e.target.value)}
                className="bg-surface border-border text-sm"
              />
            </div>

            {/* Status + Severity row */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Status</Label>
                <Select
                  value={editDraft.is_active ? "active" : "inactive"}
                  onValueChange={(v) => updateDraft("is_active", v === "active")}
                >
                  <SelectTrigger className="bg-surface border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Severity</Label>
                <Select
                  value={(editDraft.severity as string) ?? "Pending"}
                  onValueChange={(v) => updateDraft("severity", v)}
                >
                  <SelectTrigger className="bg-surface border-border text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* MITRE ATT&CK */}
            <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">MITRE ATT&CK</span>

              {/* Tactics */}
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Tactics</Label>
                <div className="flex flex-wrap gap-1 mb-1.5">
                  {((editDraft.mitre_tactics as string[]) ?? []).map((t) => (
                    <Badge key={t} variant="outline" className="text-[11px] text-teal bg-teal/10 border-teal/30 gap-1">
                      {t}
                      <button type="button" onClick={() => removeFromList("mitre_tactics", t)} className="hover:text-red-400">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <Input
                    value={newTactic}
                    onChange={(e) => setNewTactic(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_tactics", newTactic, setNewTactic))}
                    placeholder="e.g. Execution"
                    className="bg-card border-border text-sm h-7"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => addToList("mitre_tactics", newTactic, setNewTactic)}
                    className="h-7 px-2 border-border"
                  >
                    <Plus className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {/* Techniques */}
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Techniques</Label>
                <div className="flex flex-wrap gap-1 mb-1.5">
                  {((editDraft.mitre_techniques as string[]) ?? []).map((t) => (
                    <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                      {t}
                      <button type="button" onClick={() => removeFromList("mitre_techniques", t)} className="hover:text-red-400">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <Input
                    value={newTechnique}
                    onChange={(e) => setNewTechnique(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_techniques", newTechnique, setNewTechnique))}
                    placeholder="e.g. T1204"
                    className="bg-card border-border text-sm h-7"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => addToList("mitre_techniques", newTechnique, setNewTechnique)}
                    className="h-7 px-2 border-border"
                  >
                    <Plus className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {/* Sub-techniques */}
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Sub-techniques</Label>
                <div className="flex flex-wrap gap-1 mb-1.5">
                  {((editDraft.mitre_subtechniques as string[]) ?? []).map((t) => (
                    <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                      {t}
                      <button type="button" onClick={() => removeFromList("mitre_subtechniques", t)} className="hover:text-red-400">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <Input
                    value={newSubtechnique}
                    onChange={(e) => setNewSubtechnique(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("mitre_subtechniques", newSubtechnique, setNewSubtechnique))}
                    placeholder="e.g. T1204.002"
                    className="bg-card border-border text-sm h-7"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => addToList("mitre_subtechniques", newSubtechnique, setNewSubtechnique)}
                    className="h-7 px-2 border-border"
                  >
                    <Plus className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </div>

            {/* Data Sources */}
            <div className="space-y-1.5">
              <Label className="text-sm text-muted-foreground">Data Sources</Label>
              <div className="flex flex-wrap gap-1 mb-1.5">
                {((editDraft.data_sources as string[]) ?? []).map((ds) => (
                  <Badge key={ds} variant="outline" className="text-[11px] text-foreground border-border gap-1">
                    {ds}
                    <button type="button" onClick={() => removeFromList("data_sources", ds)} className="hover:text-red-400">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-1.5">
                <Input
                  value={newDataSource}
                  onChange={(e) => setNewDataSource(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToList("data_sources", newDataSource, setNewDataSource))}
                  placeholder="e.g. Endpoint File Creation Events"
                  className="bg-surface border-border text-sm"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => addToList("data_sources", newDataSource, setNewDataSource)}
                  className="h-8 px-2 border-border"
                >
                  <Plus className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditOpen(false)}
              className="border-border"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveEdit}
              disabled={patchRule.isPending || !(editDraft.name as string)?.trim()}
              className="bg-teal text-white hover:bg-teal-dim"
            >
              {patchRule.isPending ? (
                <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5 mr-1.5" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
