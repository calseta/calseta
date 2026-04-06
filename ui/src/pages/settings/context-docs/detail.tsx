import { useState } from "react";
import { useParams, useSearch, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
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
import { useContextDocument, usePatchContextDocument } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BookOpen, FileText, Globe, GitBranch, Pencil, Save, X, Target } from "lucide-react";
import {
  TargetingRuleBuilder,
  TargetingRuleDisplay,
} from "@/components/targeting-rules/targeting-rule-builder";
import {
  type TargetingRules,
  parseTargetingRules,
  serializeTargetingRules,
} from "@/components/targeting-rules/types";

export function ContextDocDetailPage() {
  const { uuid } = useParams({ strict: false }) as { uuid: string };
  const { tab: activeTab } = useSearch({ from: "/manage/context-docs/$uuid" });
  const navigate = useNavigate({ from: "/manage/context-docs/$uuid" });
  const { data, isLoading, refetch, isFetching } = useContextDocument(uuid);
  const patchDoc = usePatchContextDocument();
  const [editingRules, setEditingRules] = useState(false);
  const [draftRules, setDraftRules] = useState<TargetingRules | null>(null);

  const doc = data?.data;

  function setActiveTab(tab: string) {
    navigate({ search: { tab }, replace: true });
  }

  if (isLoading) {
    return (
      <AppLayout title="Context Document">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      </AppLayout>
    );
  }

  if (!doc) {
    return (
      <AppLayout title="Context Document">
        <div className="text-center text-dim py-20">Document not found</div>
      </AppLayout>
    );
  }

  function handleSave(content: string) {
    patchDoc.mutate(
      { uuid, body: { content } },
      {
        onSuccess: () => toast.success("Document saved"),
        onError: () => toast.error("Failed to save document"),
      },
    );
  }

  function handleSaveRules() {
    const serialized = serializeTargetingRules(draftRules);
    patchDoc.mutate(
      { uuid, body: { targeting_rules: serialized ?? null } },
      {
        onSuccess: () => {
          toast.success("Targeting rules saved");
          setEditingRules(false);
        },
        onError: () => toast.error("Failed to save targeting rules"),
      },
    );
  }

  function startEditingRules() {
    setDraftRules(parseTargetingRules(doc?.targeting_rules));
    setEditingRules(true);
  }

  const TypeIcon = doc.document_type === "runbook" ? BookOpen : FileText;

  return (
    <AppLayout title="Context Document">
      <div className="space-y-6">
        <DetailPageHeader
          backTo="/manage/context-docs"
          title={doc.title}
          onRefresh={() => refetch()}
          isRefreshing={isFetching}
          badges={
            <>
              <Badge
                variant="outline"
                className={`text-xs ${doc.is_global ? "text-amber bg-amber/10 border-amber/30" : "text-dim border-border"}`}
              >
                {doc.is_global ? "global" : "targeted"}
              </Badge>
              <Badge variant="outline" className="text-xs text-foreground border-border">
                {doc.document_type}
              </Badge>
            </>
          }
          subtitle={
            doc.description ? (
              <p className="text-sm text-muted-foreground">{doc.description}</p>
            ) : undefined
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "Scope",
              icon: Globe,
              value: (
                <Select
                  value={doc.is_global ? "global" : "targeted"}
                  onValueChange={(v) => {
                    const newIsGlobal = v === "global";
                    const body: Record<string, unknown> = { is_global: newIsGlobal };
                    if (newIsGlobal) body.targeting_rules = null;
                    patchDoc.mutate(
                      { uuid, body },
                      {
                        onSuccess: () => {
                          toast.success(newIsGlobal ? "Scope set to Global" : "Scope set to Targeted");
                          if (newIsGlobal) setEditingRules(false);
                        },
                        onError: () => toast.error("Failed to update scope"),
                      },
                    );
                  }}
                >
                  <SelectTrigger className={`h-7 w-full text-xs border ${doc.is_global ? "text-amber bg-amber/10 border-amber/30" : "text-foreground border-border"}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="global">Global</SelectItem>
                    <SelectItem value="targeted">Targeted</SelectItem>
                  </SelectContent>
                </Select>
              ),
            },
            {
              label: "Type",
              icon: TypeIcon,
              value: doc.document_type,
            },
            {
              label: "Version",
              icon: GitBranch,
              value: <span className="font-mono">v{doc.version}</span>,
            },
          ]}
        />

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-surface border border-border">
            <TabsTrigger value="content" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
              <FileText className="h-3.5 w-3.5 mr-1" />
              Content
            </TabsTrigger>
            {!doc.is_global && (
              <TabsTrigger value="targeting" className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-sm">
                <Target className="h-3.5 w-3.5 mr-1" />
                Targeting Rules
              </TabsTrigger>
            )}
          </TabsList>
          <DetailPageLayout
            sidebar={
              <DetailPageSidebar>
                <SidebarSection title="Details">
                  <DetailPageField label="UUID" value={<CopyableText text={doc.uuid} mono className="text-xs" />} />
                  <DetailPageField label="Type" value={doc.document_type} />
                  <DetailPageField label="Scope" value={doc.is_global ? "Global" : "Targeted"} />
                  <DetailPageField label="Version" value={`v${doc.version}`} />
                  <DetailPageField label="Created" value={formatDate(doc.created_at)} />
                  <DetailPageField label="Updated" value={formatDate(doc.updated_at)} />
                </SidebarSection>
                {doc.tags?.length > 0 && (
                  <SidebarSection title="Tags">
                    <div className="flex flex-wrap gap-1">
                      {doc.tags.map((t) => (
                        <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </SidebarSection>
                )}
              </DetailPageSidebar>
            }
          >

            <TabsContent value="content" className="mt-4">
              <DocumentationEditor
                content={doc.content ?? ""}
                onSave={handleSave}
                isSaving={patchDoc.isPending}
                title="Content"
                rows={20}
                placeholder="Write content in markdown..."
              />
            </TabsContent>

            {!doc.is_global && (
              <TabsContent value="targeting" className="mt-4">
                <Card className="bg-card border-border">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium text-foreground">Targeting Rules</CardTitle>
                      {!editingRules ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={startEditingRules}
                          className="h-7 text-xs text-dim hover:text-teal"
                        >
                          <Pencil className="h-3 w-3 mr-1" />
                          Edit
                        </Button>
                      ) : (
                        <div className="flex gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setEditingRules(false)}
                            className="h-7 text-xs text-dim"
                          >
                            <X className="h-3 w-3 mr-1" />
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            onClick={handleSaveRules}
                            disabled={patchDoc.isPending}
                            className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
                          >
                            <Save className="h-3 w-3 mr-1" />
                            Save
                          </Button>
                        </div>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    {editingRules ? (
                      <TargetingRuleBuilder value={draftRules} onChange={setDraftRules} />
                    ) : (
                      <TargetingRuleDisplay rules={doc.targeting_rules} />
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            )}
          </DetailPageLayout>
        </Tabs>
      </div>
    </AppLayout>
  );
}
