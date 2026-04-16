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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, Loader2 } from "lucide-react";
import type { HealthSource } from "@/lib/types";
import { useCreateHealthMetricConfig } from "@/hooks/use-api";

interface CustomMetricFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sources: HealthSource[];
  onCreated?: () => void;
}

export function CustomMetricForm({ open, onOpenChange, sources, onCreated }: CustomMetricFormProps) {
  const createConfig = useCreateHealthMetricConfig();

  const [sourceUuid, setSourceUuid] = useState("");
  const [namespace, setNamespace] = useState("");
  const [metricName, setMetricName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [statistic, setStatistic] = useState("Average");
  const [unit, setUnit] = useState("None");
  const [warningThreshold, setWarningThreshold] = useState("");
  const [criticalThreshold, setCriticalThreshold] = useState("");
  const [dimensions, setDimensions] = useState<{ key: string; value: string }[]>([]);
  const [saving, setSaving] = useState(false);

  const addDimension = () => {
    setDimensions([...dimensions, { key: "", value: "" }]);
  };

  const removeDimension = (idx: number) => {
    setDimensions(dimensions.filter((_, i) => i !== idx));
  };

  const updateDimension = (idx: number, field: "key" | "value", val: string) => {
    const updated = [...dimensions];
    updated[idx][field] = val;
    setDimensions(updated);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceUuid || !namespace || !metricName) return;
    setSaving(true);
    try {
      const dimObj: Record<string, string> = {};
      for (const d of dimensions) {
        if (d.key && d.value) dimObj[d.key] = d.value;
      }
      await createConfig.mutateAsync({
        sourceUuid,
        body: {
          display_name: displayName || `${namespace}/${metricName}`,
          namespace,
          metric_name: metricName,
          statistic,
          unit,
          dimensions: dimObj,
          category: "custom",
          warning_threshold: warningThreshold ? parseFloat(warningThreshold) : null,
          critical_threshold: criticalThreshold ? parseFloat(criticalThreshold) : null,
        },
      });
      onCreated?.();
      onOpenChange(false);
      // Reset form
      setNamespace("");
      setMetricName("");
      setDisplayName("");
      setStatistic("Average");
      setUnit("None");
      setWarningThreshold("");
      setCriticalThreshold("");
      setDimensions([]);
    } catch {
      // handled by react-query
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Custom Metric</DialogTitle>
          <DialogDescription>
            Define a custom metric to monitor from your cloud provider.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Source</Label>
            <Select value={sourceUuid} onValueChange={setSourceUuid}>
              <SelectTrigger>
                <SelectValue placeholder="Select source" />
              </SelectTrigger>
              <SelectContent>
                {sources.filter((s) => s.is_active).map((s) => (
                  <SelectItem key={s.uuid} value={s.uuid}>
                    {s.name} ({s.provider.toUpperCase()})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Namespace</Label>
              <Input value={namespace} onChange={(e) => setNamespace(e.target.value)} placeholder="AWS/ECS" required />
            </div>
            <div className="space-y-2">
              <Label>Metric Name</Label>
              <Input value={metricName} onChange={(e) => setMetricName(e.target.value)} placeholder="CPUUtilization" required />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Display Name</Label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Auto-generated if empty" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Statistic</Label>
              <Select value={statistic} onValueChange={setStatistic}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Average">Average</SelectItem>
                  <SelectItem value="Sum">Sum</SelectItem>
                  <SelectItem value="Maximum">Maximum</SelectItem>
                  <SelectItem value="Minimum">Minimum</SelectItem>
                  <SelectItem value="p99">p99</SelectItem>
                  <SelectItem value="p95">p95</SelectItem>
                  <SelectItem value="p90">p90</SelectItem>
                  <SelectItem value="p50">p50</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Unit</Label>
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="None">None</SelectItem>
                  <SelectItem value="Percent">Percent</SelectItem>
                  <SelectItem value="Count">Count</SelectItem>
                  <SelectItem value="Bytes">Bytes</SelectItem>
                  <SelectItem value="Seconds">Seconds</SelectItem>
                  <SelectItem value="Milliseconds">Milliseconds</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Warning Threshold</Label>
              <Input type="number" step="any" value={warningThreshold} onChange={(e) => setWarningThreshold(e.target.value)} placeholder="Optional" />
            </div>
            <div className="space-y-2">
              <Label>Critical Threshold</Label>
              <Input type="number" step="any" value={criticalThreshold} onChange={(e) => setCriticalThreshold(e.target.value)} placeholder="Optional" />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Dimensions</Label>
              <Button type="button" size="sm" variant="ghost" onClick={addDimension} className="h-6 text-xs gap-1">
                <Plus className="h-3 w-3" /> Add
              </Button>
            </div>
            {dimensions.map((d, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <Input
                  value={d.key}
                  onChange={(e) => updateDimension(idx, "key", e.target.value)}
                  placeholder="Key"
                  className="flex-1"
                />
                <Input
                  value={d.value}
                  onChange={(e) => updateDimension(idx, "value", e.target.value)}
                  placeholder="Value"
                  className="flex-1"
                />
                <Button type="button" size="sm" variant="ghost" onClick={() => removeDimension(idx)} className="h-8 w-8 p-0 shrink-0">
                  <Trash2 className="h-3 w-3 text-dim" />
                </Button>
              </div>
            ))}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={saving || !sourceUuid || !namespace || !metricName}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Create Metric
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
