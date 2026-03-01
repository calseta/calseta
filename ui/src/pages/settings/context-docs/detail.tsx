import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DetailPageHeader,
  DetailPageStatusCards,
  DocumentationEditor,
} from "@/components/detail-page";
import { useContextDocument, usePatchContextDocument } from "@/hooks/use-api";
import { BookOpen, FileText, Globe, GitBranch, Pencil, Save, X } from "lucide-react";
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
  const { data, isLoading } = useContextDocument(uuid);
  const patchDoc = usePatchContextDocument();
  const [editingRules, setEditingRules] = useState(false);
  const [draftRules, setDraftRules] = useState<TargetingRules | null>(null);

  const doc = data?.data;

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
          backTo="/settings/context-docs"
          title={doc.title}
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
            <div className="space-y-2">
              {doc.description && (
                <p className="text-sm text-muted-foreground">{doc.description}</p>
              )}
              {doc.tags?.length > 0 && (
                <div className="flex gap-1.5">
                  {doc.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-[11px] text-foreground border-border">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          }
        />

        <DetailPageStatusCards
          items={[
            {
              label: "Scope",
              icon: Globe,
              value: doc.is_global ? "Global" : "Targeted",
            },
            {
              label: "Version",
              icon: GitBranch,
              value: <span className="font-mono">v{doc.version}</span>,
            },
          ]}
        />

        {!doc.is_global && (
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
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
        )}

        <DocumentationEditor
          content={doc.content ?? ""}
          onSave={handleSave}
          isSaving={patchDoc.isPending}
          title="Content"
          rows={20}
          placeholder="Write content in markdown..."
        />
      </div>
    </AppLayout>
  );
}
