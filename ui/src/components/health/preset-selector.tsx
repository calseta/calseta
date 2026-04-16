import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Server,
  Database,
  Layers,
  Globe,
  Zap,
  Cloud,
  Box,
  Loader2,
  ArrowLeft,
  Search,
} from "lucide-react";
import type { HealthSource } from "@/lib/types";
import { useApplyPreset } from "@/hooks/use-api";

const AWS_PRESETS = [
  { name: "ecs", label: "ECS (Containers)", icon: Box, description: "CPU, memory, task count" },
  { name: "rds", label: "RDS (Database)", icon: Database, description: "CPU, connections, storage, latency" },
  { name: "sqs", label: "SQS (Queue)", icon: Layers, description: "Queue depth, message age, throughput" },
  { name: "alb", label: "ALB (Load Balancer)", icon: Globe, description: "Requests, response time, 5xx errors" },
  { name: "lambda", label: "Lambda (Functions)", icon: Zap, description: "Invocations, errors, duration, throttles" },
];

const AZURE_PRESETS = [
  { name: "app_service", label: "App Service", icon: Server, description: "CPU, memory, HTTP errors" },
  { name: "azure_sql", label: "Azure SQL", icon: Database, description: "CPU, DTU, storage" },
  { name: "service_bus", label: "Service Bus", icon: Layers, description: "Active messages, dead-lettered" },
  { name: "application_gateway", label: "App Gateway", icon: Globe, description: "Requests, errors, status codes" },
];

interface DiscoveredResource {
  name: string;
  arn?: string;
  dimensions: Record<string, string>;
}

interface PresetSelectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sources: HealthSource[];
  onApplied?: () => void;
}

type Step = "select" | "discover" | "confirm";

export function PresetSelector({ open, onOpenChange, sources, onApplied }: PresetSelectorProps) {
  const [selectedSourceUuid, setSelectedSourceUuid] = useState<string>("");
  const [step, setStep] = useState<Step>("select");
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredResource[]>([]);
  const [selectedResources, setSelectedResources] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);
  const applyPreset = useApplyPreset();

  const selectedSource = sources.find((s) => s.uuid === selectedSourceUuid);
  const presets = selectedSource?.provider === "aws" ? AWS_PRESETS
    : selectedSource?.provider === "azure" ? AZURE_PRESETS
    : [];

  const handleClose = (value: boolean) => {
    if (!value) {
      setStep("select");
      setSelectedPreset(null);
      setDiscovered([]);
      setSelectedResources(new Set());
    }
    onOpenChange(value);
  };

  const handleSelectPreset = async (presetName: string) => {
    if (!selectedSourceUuid) return;
    setSelectedPreset(presetName);
    setDiscovering(true);
    setStep("discover");

    try {
      const resp = await fetch(
        `/api/v1/health/sources/${selectedSourceUuid}/discover?preset=${presetName}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem("calseta_api_key") ?? ""}` } },
      );
      if (resp.ok) {
        const data = await resp.json();
        const resources: DiscoveredResource[] = data.data?.resources ?? data.resources ?? [];
        setDiscovered(resources);
        // Select all by default
        setSelectedResources(new Set(resources.map((_, i) => i)));
      } else {
        // Discovery not available or failed — fall back to applying all
        setDiscovered([]);
        setSelectedResources(new Set());
      }
    } catch {
      setDiscovered([]);
      setSelectedResources(new Set());
    } finally {
      setDiscovering(false);
    }
  };

  const toggleResource = (idx: number) => {
    const next = new Set(selectedResources);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setSelectedResources(next);
  };

  const handleApply = async () => {
    if (!selectedSourceUuid || !selectedPreset) return;
    setApplying(true);
    try {
      await applyPreset.mutateAsync({
        sourceUuid: selectedSourceUuid,
        presetName: selectedPreset,
      });
      onApplied?.();
      handleClose(false);
    } catch {
      // Error surfaced by react-query
    } finally {
      setApplying(false);
    }
  };

  const presetMeta = presets.find((p) => p.name === selectedPreset);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {step !== "select" && (
              <button
                onClick={() => { setStep("select"); setSelectedPreset(null); setDiscovered([]); }}
                className="inline-flex mr-2 text-dim hover:text-foreground align-middle"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
            )}
            {step === "select" ? "Service Monitoring" : presetMeta?.label ?? "Discovered Resources"}
          </DialogTitle>
          <DialogDescription>
            {step === "select"
              ? "Select a cloud source and service type to discover resources."
              : step === "discover" && discovering
                ? "Scanning your account for resources..."
                : `Found ${discovered.length} resource${discovered.length !== 1 ? "s" : ""}. Select which to monitor.`}
          </DialogDescription>
        </DialogHeader>

        {step === "select" && (
          <div className="space-y-4">
            {sources.length === 0 ? (
              <div className="text-sm text-dim py-4 text-center">
                No health sources configured. Add a source first via Configure Sources.
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <label className="micro-label">Cloud Source</label>
                  <Select value={selectedSourceUuid} onValueChange={setSelectedSourceUuid}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a health source" />
                    </SelectTrigger>
                    <SelectContent>
                      {sources.filter((s) => s.is_active).map((s) => (
                        <SelectItem key={s.uuid} value={s.uuid}>
                          <div className="flex items-center gap-2">
                            <Cloud className="h-3.5 w-3.5 text-dim" />
                            <span>{s.name}</span>
                            <span className="text-dim text-xs">({s.provider.toUpperCase()})</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedSource && (
                  <div className="space-y-2">
                    <label className="micro-label">Service Type</label>
                    <div className="grid gap-2">
                      {presets.map((preset) => {
                        const Icon = preset.icon;
                        return (
                          <button
                            key={preset.name}
                            onClick={() => handleSelectPreset(preset.name)}
                            className="flex items-center gap-3 rounded-lg border border-border p-3 text-left hover:border-teal/30 hover:bg-teal/5 transition-colors"
                          >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal/10">
                              <Icon className="h-4 w-4 text-teal" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-foreground">{preset.label}</p>
                              <p className="text-xs text-dim">{preset.description}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {step === "discover" && (
          <div className="space-y-3">
            {discovering ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <Loader2 className="h-6 w-6 text-teal animate-spin" />
                <p className="text-sm text-dim">
                  <Search className="h-3.5 w-3.5 inline mr-1" />
                  Discovering {presetMeta?.label} resources...
                </p>
              </div>
            ) : discovered.length === 0 ? (
              <div className="py-8 text-center space-y-2">
                <p className="text-sm text-dim">
                  No resources discovered, or discovery is not available for this preset.
                </p>
                <p className="text-xs text-dim">
                  Metrics will be created for all resources matching the preset pattern.
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <label className="micro-label">Resources</label>
                  <button
                    className="text-xs text-teal hover:underline"
                    onClick={() => {
                      if (selectedResources.size === discovered.length) {
                        setSelectedResources(new Set());
                      } else {
                        setSelectedResources(new Set(discovered.map((_, i) => i)));
                      }
                    }}
                  >
                    {selectedResources.size === discovered.length ? "Deselect all" : "Select all"}
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto space-y-1.5 rounded-md border border-border p-2">
                  {discovered.map((resource, idx) => (
                    <label
                      key={idx}
                      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-[var(--surface-2)] cursor-pointer"
                    >
                      <Checkbox
                        checked={selectedResources.has(idx)}
                        onCheckedChange={() => toggleResource(idx)}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-foreground truncate">{resource.name}</p>
                        {resource.arn && (
                          <p className="text-[10px] text-dim font-mono truncate">{resource.arn}</p>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              </>
            )}

            <DialogFooter>
              <Button
                onClick={handleApply}
                disabled={applying || discovering}
                className="w-full"
              >
                {applying && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                {discovered.length > 0
                  ? `Monitor ${selectedResources.size} resource${selectedResources.size !== 1 ? "s" : ""}`
                  : "Apply preset"}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
