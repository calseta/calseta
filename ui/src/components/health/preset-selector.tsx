import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Server,
  Database,
  Layers,
  Globe,
  Zap,
  Cloud,
  Box,
  Loader2,
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

interface PresetSelectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sources: HealthSource[];
  onApplied?: () => void;
}

export function PresetSelector({ open, onOpenChange, sources, onApplied }: PresetSelectorProps) {
  const [selectedSourceUuid, setSelectedSourceUuid] = useState<string>("");
  const [applying, setApplying] = useState<string | null>(null);
  const applyPreset = useApplyPreset();

  const selectedSource = sources.find((s) => s.uuid === selectedSourceUuid);
  const presets = selectedSource?.provider === "aws" ? AWS_PRESETS
    : selectedSource?.provider === "azure" ? AZURE_PRESETS
    : [];

  const handleApply = async (presetName: string) => {
    if (!selectedSourceUuid) return;
    setApplying(presetName);
    try {
      await applyPreset.mutateAsync({ sourceUuid: selectedSourceUuid, presetName });
      onApplied?.();
      onOpenChange(false);
    } catch {
      // Error is surfaced by react-query
    } finally {
      setApplying(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Service Monitoring</DialogTitle>
          <DialogDescription>
            Select a cloud source and apply a monitoring preset to auto-configure metrics.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {sources.length === 0 ? (
            <div className="text-sm text-dim py-4 text-center">
              No health sources configured. Add a source first via Configure Sources.
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">Cloud Source</label>
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
                  <label className="text-xs text-muted-foreground">Available Presets</label>
                  <div className="grid gap-2">
                    {presets.map((preset) => {
                      const Icon = preset.icon;
                      const isApplying = applying === preset.name;
                      return (
                        <button
                          key={preset.name}
                          onClick={() => handleApply(preset.name)}
                          disabled={!!applying}
                          className="flex items-center gap-3 rounded-lg border border-border p-3 text-left hover:border-teal/30 hover:bg-teal/5 transition-colors disabled:opacity-50"
                        >
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal/10">
                            {isApplying ? (
                              <Loader2 className="h-4 w-4 text-teal animate-spin" />
                            ) : (
                              <Icon className="h-4 w-4 text-teal" />
                            )}
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
      </DialogContent>
    </Dialog>
  );
}
