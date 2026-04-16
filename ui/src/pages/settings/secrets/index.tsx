import { useState } from "react";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useSecrets, useCreateSecret, useRotateSecret, useDeleteSecret } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import type { Secret } from "@/lib/types";

function providerBadgeClass(provider: string): string {
  switch (provider) {
    case "local_encrypted":
      return "text-teal bg-teal/10 border-teal/30";
    case "env_var":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function providerLabel(provider: string): string {
  switch (provider) {
    case "local_encrypted":
      return "Encrypted";
    case "env_var":
      return "Env Var";
    default:
      return provider;
  }
}

function SecretRow({
  secret,
  onRotate,
  onDelete,
}: {
  secret: Secret;
  onRotate: (secret: Secret) => void;
  onDelete: (secret: Secret) => void;
}) {
  return (
    <tr className="border-b border-border last:border-0 group">
      <td className="py-2.5 px-3">
        <span className="font-mono text-xs text-foreground">{secret.name}</span>
      </td>
      <td className="py-2.5 px-3">
        <Badge
          variant="outline"
          className={cn("text-[10px]", providerBadgeClass(secret.provider))}
        >
          {providerLabel(secret.provider)}
        </Badge>
      </td>
      <td className="py-2.5 px-3 text-sm text-dim max-w-[200px] truncate">
        {secret.description ?? <span className="text-border">—</span>}
      </td>
      <td className="py-2.5 px-3 text-center">
        <span className="text-xs text-dim tabular-nums">v{secret.current_version}</span>
      </td>
      <td className="py-2.5 px-3 text-sm text-dim whitespace-nowrap">
        {formatDate(secret.created_at)}
      </td>
      <td className="py-2.5 px-3">
        <div className="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
          {secret.provider === "local_encrypted" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-dim hover:text-amber"
              onClick={() => onRotate(secret)}
              title="Rotate secret"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-dim hover:text-red-threat"
            onClick={() => onDelete(secret)}
            title="Delete secret"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function SecretRowSkeleton() {
  return (
    <tr className="border-b border-border">
      <td className="py-2.5 px-3">
        <Skeleton className="h-4 w-32" />
      </td>
      <td className="py-2.5 px-3">
        <Skeleton className="h-5 w-20" />
      </td>
      <td className="py-2.5 px-3">
        <Skeleton className="h-4 w-48" />
      </td>
      <td className="py-2.5 px-3">
        <Skeleton className="h-4 w-8 mx-auto" />
      </td>
      <td className="py-2.5 px-3">
        <Skeleton className="h-4 w-32" />
      </td>
      <td className="py-2.5 px-3" />
    </tr>
  );
}

export function SecretsPage() {
  const [showAdd, setShowAdd] = useState(false);
  const [rotateTarget, setRotateTarget] = useState<Secret | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Secret | null>(null);

  // Add form
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formProvider, setFormProvider] = useState<"local_encrypted" | "env_var" | "">("");
  const [formValue, setFormValue] = useState("");
  const [formEnvVar, setFormEnvVar] = useState("");

  // Rotate form
  const [rotateValue, setRotateValue] = useState("");

  const { data, isLoading, refetch, isFetching } = useSecrets({ page_size: 200 });
  const createSecret = useCreateSecret();
  const rotateSecret = useRotateSecret();
  const deleteSecret = useDeleteSecret();

  const secrets = data?.data ?? [];

  function resetAddForm() {
    setFormName("");
    setFormDescription("");
    setFormProvider("");
    setFormValue("");
    setFormEnvVar("");
  }

  function handleAdd() {
    if (!formName.trim()) {
      toast.error("Name is required");
      return;
    }
    if (!formProvider) {
      toast.error("Provider is required");
      return;
    }
    if (formProvider === "local_encrypted" && !formValue.trim()) {
      toast.error("Value is required for encrypted secrets");
      return;
    }
    if (formProvider === "env_var" && !formEnvVar.trim()) {
      toast.error("Environment variable name is required");
      return;
    }

    const body: Record<string, unknown> = {
      name: formName.trim(),
      provider: formProvider,
    };
    if (formDescription.trim()) body.description = formDescription.trim();
    if (formProvider === "local_encrypted") body.value = formValue;
    if (formProvider === "env_var") body.env_var_name = formEnvVar.trim();

    createSecret.mutate(body, {
      onSuccess: () => {
        toast.success("Secret created");
        setShowAdd(false);
        resetAddForm();
      },
      onError: () => toast.error("Failed to create secret"),
    });
  }

  function handleRotate() {
    if (!rotateTarget) return;
    if (!rotateValue.trim()) {
      toast.error("New value is required");
      return;
    }
    rotateSecret.mutate(
      { uuid: rotateTarget.uuid, value: rotateValue },
      {
        onSuccess: () => {
          toast.success("Secret rotated");
          setRotateTarget(null);
          setRotateValue("");
        },
        onError: () => toast.error("Failed to rotate secret"),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    deleteSecret.mutate(deleteTarget.uuid, {
      onSuccess: () => {
        toast.success("Secret deleted");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Failed to delete secret"),
    });
  }

  return (
    <AppLayout title="Secrets">
      <div className="space-y-4">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            <span className="text-[11px] text-dim">{secrets.length} secret(s)</span>
          </div>
          <Button size="sm" onClick={() => setShowAdd(true)} className="h-8 gap-1">
            <Plus className="h-3.5 w-3.5" />
            Add Secret
          </Button>
        </div>

        {/* Table */}
        {isLoading ? (
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="py-2 px-3 text-left micro-label">Name</th>
                    <th className="py-2 px-3 text-left micro-label">Provider</th>
                    <th className="py-2 px-3 text-left micro-label">Description</th>
                    <th className="py-2 px-3 text-center micro-label">Version</th>
                    <th className="py-2 px-3 text-left micro-label">Created</th>
                    <th className="py-2 px-3" />
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <SecretRowSkeleton key={i} />
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        ) : secrets.length === 0 ? (
          <Card>
            <CardContent className="py-20 text-center">
              <p className="text-sm text-dim">No secrets configured</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="py-2 px-3 text-left micro-label">
                      Name
                    </th>
                    <th className="py-2 px-3 text-left micro-label">
                      Provider
                    </th>
                    <th className="py-2 px-3 text-left micro-label">
                      Description
                    </th>
                    <th className="py-2 px-3 text-center micro-label">
                      Version
                    </th>
                    <th className="py-2 px-3 text-left micro-label">
                      Created
                    </th>
                    <th className="py-2 px-3" />
                  </tr>
                </thead>
                <tbody>
                  {secrets.map((s) => (
                    <SecretRow
                      key={s.uuid}
                      secret={s}
                      onRotate={setRotateTarget}
                      onDelete={setDeleteTarget}
                    />
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Add Secret Dialog */}
      <Dialog
        open={showAdd}
        onOpenChange={(open) => {
          setShowAdd(open);
          if (!open) resetAddForm();
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add Secret</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="secret-name" className="micro-label">Name *</Label>
              <Input
                id="secret-name"
                placeholder="MY_SECRET_NAME"
                className="font-mono"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="secret-description" className="micro-label">Description</Label>
              <Input
                id="secret-description"
                placeholder="What is this secret used for?"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="micro-label">Provider *</Label>
              <Select
                value={formProvider}
                onValueChange={(v) => setFormProvider(v as "local_encrypted" | "env_var")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="local_encrypted">Encrypted (stored in DB)</SelectItem>
                  <SelectItem value="env_var">Env Var (reference only)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {formProvider === "local_encrypted" && (
              <div className="space-y-1.5">
                <Label htmlFor="secret-value" className="micro-label">Value *</Label>
                <Input
                  id="secret-value"
                  type="password"
                  placeholder="Enter secret value"
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  autoComplete="new-password"
                />
              </div>
            )}

            {formProvider === "env_var" && (
              <div className="space-y-1.5">
                <Label htmlFor="secret-env-var" className="micro-label">Environment Variable Name *</Label>
                <Input
                  id="secret-env-var"
                  placeholder="MY_ENV_VAR"
                  className="font-mono"
                  value={formEnvVar}
                  onChange={(e) => setFormEnvVar(e.target.value)}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowAdd(false);
                resetAddForm();
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={createSecret.isPending}>
              {createSecret.isPending ? "Creating..." : "Create Secret"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rotate Secret Dialog */}
      <Dialog
        open={rotateTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRotateTarget(null);
            setRotateValue("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Rotate Secret</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-dim">
              Rotating{" "}
              <span className="font-mono text-foreground">{rotateTarget?.name}</span>. The
              previous value will be replaced.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="rotate-value" className="micro-label">New Value *</Label>
              <Input
                id="rotate-value"
                type="password"
                placeholder="Enter new secret value"
                value={rotateValue}
                onChange={(e) => setRotateValue(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRotateTarget(null);
                setRotateValue("");
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleRotate} disabled={rotateSecret.isPending}>
              {rotateSecret.isPending ? "Rotating..." : "Rotate Secret"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete Secret"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </AppLayout>
  );
}
