import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ResizableTable,
  ResizableTableHead,
  type ColumnDef,
} from "@/components/ui/resizable-table";
import { TablePagination } from "@/components/table-pagination";
import {
  useLLMIntegrations,
  useCreateLLMIntegration,
} from "@/hooks/use-api";
import { useTableState } from "@/hooks/use-table-state";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Plus, RefreshCw, Check } from "lucide-react";

const COLUMNS: ColumnDef[] = [
  { key: "provider", initialWidth: 120, minWidth: 90 },
  { key: "name", initialWidth: 240, minWidth: 140 },
  { key: "model", initialWidth: 200, minWidth: 120 },
  { key: "default", initialWidth: 80, minWidth: 70 },
  { key: "api_key", initialWidth: 100, minWidth: 80 },
  { key: "input_cost", initialWidth: 130, minWidth: 100 },
  { key: "output_cost", initialWidth: 130, minWidth: 100 },
  { key: "created", initialWidth: 150, minWidth: 100 },
];

const PROVIDERS = [
  "anthropic",
  "openai",
  "azure_openai",
  "claude_code",
  "aws_bedrock",
  "ollama",
] as const;

type Provider = (typeof PROVIDERS)[number];

const PROVIDER_DISPLAY: Record<Provider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  azure_openai: "Azure OpenAI",
  claude_code: "Claude Code",
  aws_bedrock: "AWS Bedrock",
  ollama: "Ollama",
};

function providerLabel(p: string): string {
  return PROVIDER_DISPLAY[p as Provider] ?? p;
}

function providerBadgeClass(p: string): string {
  switch (p) {
    case "anthropic":
      return "text-amber bg-amber/10 border-amber/30";
    case "openai":
      return "text-teal bg-teal/10 border-teal/30";
    case "azure_openai":
      return "text-blue-400 bg-blue-400/10 border-blue-400/30";
    case "claude_code":
      return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "aws_bedrock":
      return "text-amber bg-amber/10 border-amber/30";
    case "ollama":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

interface CreateFormState {
  name: string;
  provider: Provider | "";
  model: string;
  api_key_ref: string;
  base_url: string;
  is_default: boolean;
}

const EMPTY_FORM: CreateFormState = {
  name: "",
  provider: "",
  model: "",
  api_key_ref: "",
  base_url: "",
  is_default: false,
};

export function LLMIntegrationsPage() {
  const { page, setPage, pageSize, handlePageSizeChange, params } =
    useTableState({});

  const { data, isLoading, refetch, isFetching } = useLLMIntegrations(params);
  const createIntegration = useCreateLLMIntegration();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CreateFormState>(EMPTY_FORM);

  const integrations = data?.data ?? [];
  const meta = data?.meta;

  function handleOpen(v: boolean) {
    setOpen(v);
    if (!v) setForm(EMPTY_FORM);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.provider) {
      toast.error("Select a provider");
      return;
    }
    if (!form.name.trim() || !form.model.trim()) {
      toast.error("Name and model are required");
      return;
    }
    if (form.provider === "azure_openai" && !form.base_url.trim()) {
      toast.error("Base URL is required for Azure OpenAI");
      return;
    }

    const body: Record<string, unknown> = {
      name: form.name.trim(),
      provider: form.provider,
      model: form.model.trim(),
      is_default: form.is_default,
    };
    if (form.api_key_ref.trim()) {
      body.api_key_ref = form.api_key_ref.trim();
    }
    if (form.base_url.trim()) {
      body.base_url = form.base_url.trim();
    }

    createIntegration.mutate(body, {
      onSuccess: (res) => {
        toast.success("LLM integration created");
        handleOpen(false);
        const uuid = res?.data?.uuid;
        if (uuid) {
          navigate({ to: "/manage/llm-integrations/$uuid", params: { uuid } });
        }
      },
      onError: () => toast.error("Failed to create LLM integration"),
    });
  }

  return (
    <AppLayout title="LLM Integrations">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
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
            {meta && (
              <span className="text-xs text-dim">
                {meta.total} integration{meta.total !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <Button
            size="sm"
            className="bg-teal text-white hover:bg-teal-dim"
            onClick={() => setOpen(true)}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Add Integration
          </Button>
        </div>

        <div className="rounded-lg border border-border bg-card">
          <ResizableTable storageKey="llm-integrations" columns={COLUMNS}>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <ResizableTableHead columnKey="provider" className="text-dim text-xs">Provider</ResizableTableHead>
                <ResizableTableHead columnKey="name" className="text-dim text-xs">Name</ResizableTableHead>
                <ResizableTableHead columnKey="model" className="text-dim text-xs">Model</ResizableTableHead>
                <ResizableTableHead columnKey="default" className="text-dim text-xs">Default</ResizableTableHead>
                <ResizableTableHead columnKey="api_key" className="text-dim text-xs">API Key</ResizableTableHead>
                <ResizableTableHead columnKey="input_cost" className="text-dim text-xs">Input / 1k tokens</ResizableTableHead>
                <ResizableTableHead columnKey="output_cost" className="text-dim text-xs">Output / 1k tokens</ResizableTableHead>
                <ResizableTableHead columnKey="created" className="text-dim text-xs">Created</ResizableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-36" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-14" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-14" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-28" /></TableCell>
                    </TableRow>
                  ))
                : integrations.map((integration) => (
                    <TableRow
                      key={integration.uuid}
                      className="border-border hover:bg-accent/50 cursor-pointer"
                      onClick={() =>
                        navigate({
                          to: "/manage/llm-integrations/$uuid",
                          params: { uuid: integration.uuid },
                        })
                      }
                    >
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[11px]", providerBadgeClass(integration.provider))}
                        >
                          {providerLabel(integration.provider)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm font-medium text-foreground">
                        {integration.name}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground font-mono">
                        {integration.model}
                      </TableCell>
                      <TableCell>
                        {integration.is_default && (
                          <Badge
                            variant="outline"
                            className="text-[11px] text-teal bg-teal/10 border-teal/30"
                          >
                            default
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {integration.api_key_ref_set ? (
                          <Check className="h-3.5 w-3.5 text-teal" />
                        ) : (
                          <span className="text-xs text-dim">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {integration.cost_per_1k_input_tokens_cents}¢
                      </TableCell>
                      <TableCell className="text-xs text-dim">
                        {integration.cost_per_1k_output_tokens_cents}¢
                      </TableCell>
                      <TableCell className="text-xs text-dim whitespace-nowrap">
                        {formatDate(integration.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && integrations.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-dim py-20">
                    No LLM integrations configured
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </ResizableTable>
        </div>

        {meta && (
          <TablePagination
            page={page}
            pageSize={pageSize}
            totalPages={meta.total_pages}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        )}
      </div>

      <Dialog open={open} onOpenChange={handleOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add LLM Integration</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            <div className="space-y-1.5">
              <Label htmlFor="llm-name">Name</Label>
              <Input
                id="llm-name"
                placeholder="e.g. Claude Sonnet Production"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="llm-provider">Provider</Label>
              <Select
                value={form.provider}
                onValueChange={(v) => setForm((f) => ({ ...f, provider: v as Provider }))}
              >
                <SelectTrigger id="llm-provider">
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {PROVIDER_DISPLAY[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="llm-model">Model</Label>
              <Input
                id="llm-model"
                placeholder="e.g. claude-sonnet-4-5"
                value={form.model}
                onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
                required
              />
            </div>

            {form.provider === "azure_openai" && (
              <div className="space-y-1.5">
                <Label htmlFor="llm-base-url">Base URL</Label>
                <Input
                  id="llm-base-url"
                  placeholder="https://{resource}.openai.azure.com/"
                  value={form.base_url}
                  onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                  required
                />
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="llm-api-key-ref">
                API Key Env Var{" "}
                <span className="text-dim font-normal">(optional)</span>
              </Label>
              <Input
                id="llm-api-key-ref"
                placeholder="e.g. ANTHROPIC_API_KEY"
                value={form.api_key_ref}
                onChange={(e) => setForm((f) => ({ ...f, api_key_ref: e.target.value }))}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                id="llm-is-default"
                type="checkbox"
                className="rounded border-border"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              <Label htmlFor="llm-is-default" className="cursor-pointer font-normal">
                Set as default integration
              </Label>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                className="bg-teal text-white hover:bg-teal-dim"
                disabled={createIntegration.isPending}
              >
                {createIntegration.isPending ? "Creating..." : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
