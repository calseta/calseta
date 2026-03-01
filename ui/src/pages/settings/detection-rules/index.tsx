import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  useDetectionRules,
  useCreateDetectionRule,
  useDeleteDetectionRule,
} from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { Plus, Trash2 } from "lucide-react";

export function DetectionRulesPage() {
  const { data, isLoading } = useDetectionRules({ page_size: 100 });
  const createRule = useCreateDetectionRule();
  const deleteRule = useDeleteDetectionRule();
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ uuid: string; name: string } | null>(null);

  const rules = data?.data ?? [];

  function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);

    const tacticsRaw = (fd.get("mitre_tactics") as string).trim();
    const techniquesRaw = (fd.get("mitre_techniques") as string).trim();
    const subtechniquesRaw = (fd.get("mitre_subtechniques") as string).trim();
    const dataSourcesRaw = (fd.get("data_sources") as string).trim();

    createRule.mutate(
      {
        name: fd.get("name") as string,
        source_rule_id: (fd.get("source_rule_id") as string) || undefined,
        source_name: (fd.get("source_name") as string) || undefined,
        severity: (fd.get("severity") as string) || undefined,
        mitre_tactics: tacticsRaw ? tacticsRaw.split(",").map((s) => s.trim()) : [],
        mitre_techniques: techniquesRaw ? techniquesRaw.split(",").map((s) => s.trim()) : [],
        mitre_subtechniques: subtechniquesRaw ? subtechniquesRaw.split(",").map((s) => s.trim()) : [],
        data_sources: dataSourcesRaw ? dataSourcesRaw.split(",").map((s) => s.trim()) : [],
        run_frequency: (fd.get("run_frequency") as string) || undefined,
        created_by: (fd.get("created_by") as string) || undefined,
        documentation: (fd.get("documentation") as string) || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          toast.success("Detection rule created");
        },
        onError: () => toast.error("Failed to create detection rule"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteRule.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Detection rule deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete detection rule"),
    });
  }

  return (
    <AppLayout title="Detection Rules">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-xs text-dim">
            {data?.meta?.total ?? 0} rules
          </span>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-teal text-white hover:bg-teal-dim">
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add Rule
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Detection Rule</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3">
                <Field label="Name" name="name" required />
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Source Rule ID" name="source_rule_id" />
                  <Field label="Source Name" name="source_name" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Severity" name="severity" placeholder="e.g. High, Critical" />
                  <Field label="Run Frequency" name="run_frequency" placeholder="e.g. 5m, 1h" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Tactics</Label>
                  <Input name="mitre_tactics" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: Initial Access, Execution" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Techniques</Label>
                  <Input name="mitre_techniques" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: T1566, T1059" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">MITRE Sub-techniques</Label>
                  <Input name="mitre_subtechniques" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: T1566.001, T1059.001" />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Data Sources</Label>
                  <Input name="data_sources" className="mt-1 bg-surface border-border text-sm" placeholder="Comma-separated: Process, Network Traffic" />
                </div>
                <Field label="Created By" name="created_by" placeholder="Author name or team" />
                <div>
                  <Label className="text-xs text-muted-foreground">Documentation</Label>
                  <Textarea name="documentation" className="mt-1 bg-surface border-border text-sm" rows={3} />
                </div>
                <Button type="submit" disabled={createRule.isPending} className="w-full bg-teal text-white hover:bg-teal-dim">
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-dim text-xs">Name</TableHead>
                <TableHead className="text-dim text-xs">Source</TableHead>
                <TableHead className="text-dim text-xs">Severity</TableHead>
                <TableHead className="text-dim text-xs">MITRE</TableHead>
                <TableHead className="text-dim text-xs">Created</TableHead>
                <TableHead className="text-dim text-xs w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 6 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-5 w-20" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : rules.map((rule) => (
                    <TableRow key={rule.uuid} className="border-border hover:bg-accent/50">
                      <TableCell>
                        <Link
                          to="/settings/detection-rules/$uuid"
                          params={{ uuid: rule.uuid }}
                          className="text-sm text-foreground hover:text-teal-light transition-colors"
                        >
                          {rule.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{rule.source_name ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{rule.severity ?? "—"}</TableCell>
                      <TableCell className="text-xs text-dim">
                        {rule.mitre_tactics?.length > 0 && <span>{rule.mitre_tactics.join(", ")}</span>}
                        {rule.mitre_techniques?.length > 0 && <span className="ml-1">/ {rule.mitre_techniques.join(", ")}</span>}
                        {!rule.mitre_tactics?.length && !rule.mitre_techniques?.length && "—"}
                      </TableCell>
                      <TableCell className="text-xs text-dim">{relativeTime(rule.created_at)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget({ uuid: rule.uuid, name: rule.name })}
                          className="h-8 w-8 p-0 text-dim hover:text-red-threat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && rules.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-dim py-12">
                    No detection rules configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete Detection Rule"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}

function Field({
  label,
  name,
  required,
  placeholder,
}: {
  label: string;
  name: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input name={name} required={required} placeholder={placeholder} className="mt-1 bg-surface border-border text-sm" />
    </div>
  );
}
